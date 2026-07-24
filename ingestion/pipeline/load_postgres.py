import json
from pathlib import Path

import asyncpg
import jsonschema

from ingestion.pipeline import parse_source, schema_checker, validate_extraction

SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text()

_MIGRATION_ADD_SCHEMA_CHECK = """
ALTER TABLE curation_items ADD COLUMN IF NOT EXISTS schema_check JSONB;
"""

# Groups per-element curation_items into one reviewable proposal (statement).
# NULL = legacy ungrouped item; backward-compatible.
_MIGRATION_ADD_GROUP_ID = """
ALTER TABLE curation_items ADD COLUMN IF NOT EXISTS group_id TEXT;
"""


async def ensure_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(SCHEMA_SQL)
    await conn.execute(_MIGRATION_ADD_SCHEMA_CHECK)
    await conn.execute(_MIGRATION_ADD_GROUP_ID)


async def upsert_documents(conn: asyncpg.Connection, documents: list[dict]) -> None:
    for doc in documents:
        await conn.execute(
            """
            INSERT INTO documents (doc_id, title, topic, grade_level, source_type)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (doc_id) DO UPDATE SET
                title = EXCLUDED.title,
                topic = EXCLUDED.topic,
                grade_level = EXCLUDED.grade_level,
                source_type = EXCLUDED.source_type,
                updated_at = now()
            """,
            doc["doc_id"],
            doc["title"],
            doc["topic"],
            doc["grade_level"],
            doc["source_type"],
        )


async def upsert_chunks(conn: asyncpg.Connection, chunks: list[dict]) -> None:
    for chunk in chunks:
        await conn.execute(
            """
            INSERT INTO chunks (chunk_id, doc_id, content, concept_ids, topic, grade_level, source_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (chunk_id) DO UPDATE SET
                content = EXCLUDED.content,
                concept_ids = EXCLUDED.concept_ids,
                topic = EXCLUDED.topic,
                grade_level = EXCLUDED.grade_level,
                source_type = EXCLUDED.source_type
            """,
            chunk["chunk_id"],
            chunk["doc_id"],
            chunk["content"],
            json.dumps(chunk["concept_ids"]),
            chunk["topic"],
            chunk["grade_level"],
            chunk["source_type"],
        )


async def delete_chunks_for_doc(conn: asyncpg.Connection, doc_id: str) -> None:
    """Remove a document's existing chunks before a re-ingest.

    A re-run may pick a different chunk strategy, so chunk ids/counts change and
    a plain upsert would leave stale rows. Deletes are scoped to ``doc_id``.
    """
    await conn.execute("DELETE FROM chunks WHERE doc_id = $1", doc_id)


async def start_ingestion_job(conn: asyncpg.Connection, job_id: str, source_path: str) -> None:
    await conn.execute(
        "INSERT INTO ingestion_jobs (job_id, status, source_path) VALUES ($1, 'running', $2)",
        job_id,
        source_path,
    )


async def finish_ingestion_job(
    conn: asyncpg.Connection,
    job_id: str,
    status: str,
    stats: dict,
    error_message: str | None,
) -> None:
    await conn.execute(
        """
        UPDATE ingestion_jobs
        SET status = $2, stats = $3, error_message = $4, finished_at = now()
        WHERE job_id = $1
        """,
        job_id,
        status,
        json.dumps(stats),
        error_message,
    )


async def stage_extraction_output(
    conn: asyncpg.Connection, candidate: dict
) -> tuple[bool, str | None, int, int]:
    """Stage validated nodes/edges as proposed curation items.

    Returns ``(ok, error, staged_nodes, staged_edges)`` where the two counts are
    rows *actually* inserted — duplicates hit ``ON CONFLICT DO NOTHING`` and are
    excluded, so callers can report an honest proposed-count.
    """
    try:
        validate_extraction.validate_extraction_output(candidate)
    except jsonschema.ValidationError as exc:
        return False, str(exc), 0, 0

    staged_nodes = 0
    for node in candidate["nodes"]:
        check = schema_checker.check_node(node)
        row = await conn.fetchrow(
            """
            INSERT INTO curation_items (item_id, item_type, action, payload, status, proposed_by, schema_check)
            VALUES ($1, 'node', 'create', $2, 'proposed', 'llm', $3)
            ON CONFLICT (item_id) DO NOTHING
            RETURNING item_id
            """,
            f"curation:{node['id']}",
            json.dumps(node),
            json.dumps(check),
        )
        staged_nodes += row is not None
    staged_edges = 0
    for edge in candidate["edges"]:
        check = schema_checker.check_edge(edge)
        row = await conn.fetchrow(
            """
            INSERT INTO curation_items (item_id, item_type, action, payload, status, proposed_by, schema_check)
            VALUES ($1, 'edge', 'create', $2, 'proposed', 'llm', $3)
            ON CONFLICT (item_id) DO NOTHING
            RETURNING item_id
            """,
            f"curation:{edge['id']}",
            json.dumps(edge),
            json.dumps(check),
        )
        staged_edges += row is not None
    return True, None, staged_nodes, staged_edges


_EXPERT_DEMO_CASES = parse_source.DATA_DIR / "expert_demo" / "cases.json"


async def stage_demo_review_group(
    conn: asyncpg.Connection, group_id: str, candidate: dict
) -> tuple[int, int]:
    """Stage one demo proposal group (nodes+edges of a statement) as proposed curation_items.

    All items share ``group_id`` (so the Review page assembles them into one reviewable
    statement), each carries its own ``schema_check``, and item_ids are group-scoped so the
    demo seed never collides with the extraction path. Idempotent (``ON CONFLICT DO NOTHING``).
    """
    staged_nodes = 0
    for node in candidate.get("nodes", []):
        row = await conn.fetchrow(
            """
            INSERT INTO curation_items
                (item_id, item_type, action, payload, status, proposed_by, schema_check, group_id)
            VALUES ($1, 'node', 'create', $2, 'proposed', 'demo', $3, $4)
            ON CONFLICT (item_id) DO NOTHING
            RETURNING item_id
            """,
            f"curation:{group_id}:{node['id']}",
            json.dumps(node),
            json.dumps(schema_checker.check_node(node)),
            group_id,
        )
        staged_nodes += row is not None
    staged_edges = 0
    for edge in candidate.get("edges", []):
        row = await conn.fetchrow(
            """
            INSERT INTO curation_items
                (item_id, item_type, action, payload, status, proposed_by, schema_check, group_id)
            VALUES ($1, 'edge', 'create', $2, 'proposed', 'demo', $3, $4)
            ON CONFLICT (item_id) DO NOTHING
            RETURNING item_id
            """,
            f"curation:{group_id}:{edge['id']}",
            json.dumps(edge),
            json.dumps(schema_checker.check_edge(edge)),
            group_id,
        )
        staged_edges += row is not None
    return staged_nodes, staged_edges


async def stage_demo_review_groups(conn: asyncpg.Connection, case_ids: list[str]) -> dict:
    """Seed selected expert-demo cases as proposed review groups (one group per case)."""
    cases = {c["id"]: c for c in json.loads(_EXPERT_DEMO_CASES.read_text(encoding="utf-8"))}
    staged: dict = {}
    for cid in case_ids:
        case = cases.get(cid)
        if case is None:
            continue
        proposal = case.get("proposal", {})
        candidate = {
            "nodes": proposal.get("proposed_nodes", []),
            "edges": proposal.get("proposed_edges", []),
        }
        n, e = await stage_demo_review_group(conn, f"group:{cid}", candidate)
        staged[cid] = {"nodes": n, "edges": e}
    return staged
