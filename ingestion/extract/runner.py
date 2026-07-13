"""Document-ingestion orchestrator.

Turns a raw chapter file into proposed graph nodes/edges (staged for human
curation) plus stored chunks/embeddings, in explicit deterministic stages:

    parse → chunk → (per chunk) existing-concepts lookup → prompt → LLM extract
    → schema-validate → stage to curation → collect concept_ids
    → write chunks/embeddings → job log

Design mirrors the staged, re-runnable discipline of the reference orchestrator
without its multi-agent machinery: one function, injectable resources, every
step observable. Extraction is sequential (one chunk = one LLM call) — chapter
chunk counts are small and sequential keeps ``existing_concepts`` consistent and
logs readable.

``dry_run=True`` performs parse + chunk + prompt assembly only: no LLM call, no
token spend, no DB write. It powers the ``/admin/ingest/preview`` endpoint so a
reviewer can see the chunking and the exact prompts before anything is spent.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass, field

from ingestion.extract import chunkers, llm_client
from ingestion.extract.parse_document import ParsedDocument, parse_document
from ingestion.pipeline import (
    build_extraction_prompt,
    embed_chunks,
    load_postgres,
    load_qdrant,
    validate_extraction,
)

DEFAULT_STRATEGY = "recursive"
_NO_EXISTING = "(目前無既有概念)"


@dataclass
class ChunkReport:
    chunk_id: str
    content: str
    proposed_node_ids: list[str] = field(default_factory=list)
    proposed_edge_ids: list[str] = field(default_factory=list)
    extraction_failed: bool = False
    tokens: int = 0
    # populated in dry-run previews only
    user_prompt: str | None = None


@dataclass
class IngestReport:
    job_id: str
    doc_id: str
    title: str
    status: str
    strategy: str
    chunk_params: dict
    profile: str | None
    dry_run: bool
    stats: dict
    chunks: list[ChunkReport] = field(default_factory=list)
    system_prompt: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _make_chunk_id(doc_id: str, index: int) -> str:
    return f"{doc_id}:chunk:{index:03d}"


def _chunk_row(doc: ParsedDocument, chunk_id: str, content: str, concept_ids: list[str]) -> dict:
    """Shape a chunk dict for the shared loaders / embedder."""
    return {
        "chunk_id": chunk_id,
        "doc_id": doc.doc_id,
        "content": content,
        "concept_ids": concept_ids,
        "topic": doc.topic,
        "grade_level": doc.grade_level,
        "source_type": doc.source_type,
    }


def _fetch_existing_concepts(neo4j_driver, limit: int) -> str:
    """Return an ``id: label`` list of current approved/proposed nodes.

    Fed to the prompt so the model can flag likely duplicates. Scoped by a cap
    because the demo graph is small; a larger corpus would filter by topic.
    """
    if neo4j_driver is None:
        return _NO_EXISTING
    with neo4j_driver.session() as session:
        rows = session.run(
            "MATCH (n) WHERE n.status IN ['approved', 'proposed'] "
            "RETURN n.id AS id, n.label AS label ORDER BY n.label LIMIT $limit",
            limit=limit,
        ).data()
    if not rows:
        return _NO_EXISTING
    return "\n".join(f"- {r['id']}: {r['label']}" for r in rows)


async def _extract_chunk(
    *,
    extract_fn,
    system_prompt: str,
    user_prompt: str,
    retries: int,
) -> tuple[dict | None, int]:
    """Run extraction with schema validation and a bounded retry.

    Returns ``(candidate, tokens)`` where ``candidate`` is a schema-valid dict,
    or ``(None, tokens)`` when every attempt failed to parse/validate.
    """
    tokens = 0
    for _ in range(retries + 1):
        try:
            # extract_fn is a sync/blocking call (OpenAI client) — run it off the
            # event loop so a multi-chunk ingest doesn't stall other requests.
            candidate, call_tokens = await asyncio.to_thread(extract_fn, system_prompt, user_prompt)
            tokens += call_tokens
            validate_extraction.validate_extraction_output(candidate)
            return candidate, tokens
        except llm_client.LLMNotConfigured:
            # A config error, not a per-chunk data problem: fail the whole job
            # fast rather than silently flagging every chunk as failed.
            raise
        except Exception:
            # JSON decode error, schema violation, or transient API error: retry
            # until the budget is exhausted, then flag the chunk (job continues).
            continue
    return None, tokens


async def ingest_document(
    *,
    source_path,
    strategy: str = DEFAULT_STRATEGY,
    chunk_params: dict | None = None,
    dry_run: bool = False,
    extract_fn=None,
    pg_conn=None,
    qdrant=None,
    neo4j_driver=None,
    max_existing: int = 200,
    retries: int = 1,
) -> IngestReport:
    """Ingest one chapter file. See module docstring for the stage sequence.

    ``dry_run`` needs no DB handles. A real run requires ``pg_conn`` and
    ``qdrant``; ``neo4j_driver`` is optional (missing → no existing-concept
    hints). ``extract_fn(system, user) -> (dict, tokens)`` defaults to the
    OpenAI client and is injectable for tests.
    """
    chunk_params = chunk_params or {}
    extract_fn = extract_fn or llm_client.extract
    job_id = f"ingest:{uuid.uuid4()}"

    doc = parse_document(source_path)
    chunker = chunkers.get_chunker(strategy, **chunk_params)
    pieces = chunker.chunk(doc.body)
    system_prompt = build_extraction_prompt.build_system_prompt(doc.extraction_profile)

    report = IngestReport(
        job_id=job_id,
        doc_id=doc.doc_id,
        title=doc.title,
        status="preview" if dry_run else "running",
        strategy=strategy,
        chunk_params=chunker.params(),
        profile=doc.extraction_profile,
        dry_run=dry_run,
        stats={},
        system_prompt=system_prompt,
    )

    existing_concepts = _fetch_existing_concepts(neo4j_driver, max_existing)

    # ---- dry run: assemble prompts only, no spend, no writes ------------------
    if dry_run:
        for index, content in enumerate(pieces):
            chunk_id = _make_chunk_id(doc.doc_id, index)
            report.chunks.append(
                ChunkReport(
                    chunk_id=chunk_id,
                    content=content,
                    user_prompt=build_extraction_prompt.build_user_prompt(
                        chunk_id=chunk_id,
                        existing_concepts=existing_concepts,
                        chunk_text=content,
                    ),
                )
            )
        report.status = "preview"
        report.stats = {
            "chunks": len(pieces),
            "strategy": strategy,
            "chunk_params": chunker.params(),
        }
        return report

    if pg_conn is None or qdrant is None:
        raise ValueError("a non-dry-run ingest requires pg_conn and qdrant")

    await load_postgres.ensure_schema(pg_conn)
    await load_postgres.start_ingestion_job(pg_conn, job_id, str(source_path))

    total_tokens = 0
    failed_chunks = 0
    proposed_nodes = 0
    proposed_edges = 0
    chunk_rows: list[dict] = []
    status = "success"
    error_message = None

    try:
        for index, content in enumerate(pieces):
            chunk_id = _make_chunk_id(doc.doc_id, index)
            user_prompt = build_extraction_prompt.build_user_prompt(
                chunk_id=chunk_id,
                existing_concepts=existing_concepts,
                chunk_text=content,
            )
            candidate, tokens = await _extract_chunk(
                extract_fn=extract_fn,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                retries=retries,
            )
            total_tokens += tokens

            chunk_report = ChunkReport(chunk_id=chunk_id, content=content, tokens=tokens)
            concept_ids: list[str] = []
            if candidate is None:
                chunk_report.extraction_failed = True
                failed_chunks += 1
            else:
                (
                    ok,
                    stage_error,
                    staged_nodes,
                    staged_edges,
                ) = await load_postgres.stage_extraction_output(pg_conn, candidate)
                if not ok:
                    # Should not happen (already validated), but stay defensive.
                    chunk_report.extraction_failed = True
                    failed_chunks += 1
                else:
                    node_ids = [n["id"] for n in candidate["nodes"]]
                    edge_ids = [e["id"] for e in candidate["edges"]]
                    concept_ids = node_ids
                    chunk_report.proposed_node_ids = node_ids
                    chunk_report.proposed_edge_ids = edge_ids
                    # count rows actually inserted, not proposed: duplicates hit
                    # ON CONFLICT DO NOTHING and must not inflate the stats.
                    proposed_nodes += staged_nodes
                    proposed_edges += staged_edges

            chunk_rows.append(_chunk_row(doc, chunk_id, content, concept_ids))
            report.chunks.append(chunk_report)

        # ---- persist document + chunks + embeddings --------------------------
        # Compute embeddings first: it is the most failure-prone external call
        # (may hit the OpenAI embeddings API). Doing it before any delete keeps a
        # failure from leaving the doc half-written across PG and Qdrant. Blocking
        # calls (embed, Qdrant) run off the event loop.
        embeddings = await asyncio.to_thread(embed_chunks.embed_chunks, chunk_rows)

        await load_postgres.upsert_documents(pg_conn, [doc.document_row()])
        # re-ingest may change chunk count/ids → clear the doc's old chunks first
        await load_postgres.delete_chunks_for_doc(pg_conn, doc.doc_id)
        await asyncio.to_thread(load_qdrant.delete_chunks_for_doc, qdrant, doc.doc_id)
        await load_postgres.upsert_chunks(pg_conn, chunk_rows)
        await asyncio.to_thread(load_qdrant.load_chunks, qdrant, chunk_rows, embeddings)
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
        raise
    finally:
        report.stats = {
            "chunks": len(chunk_rows),
            "proposed_nodes": proposed_nodes,
            "proposed_edges": proposed_edges,
            "failed_chunks": failed_chunks,
            "tokens": total_tokens,
            "strategy": strategy,
            "chunk_params": chunker.params(),
        }
        report.status = status
        report.error_message = error_message
        await load_postgres.finish_ingestion_job(
            pg_conn,
            job_id,
            status,
            report.stats,
            error_message,
        )

    return report
