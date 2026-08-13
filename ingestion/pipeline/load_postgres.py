import json
from datetime import datetime, timedelta
from pathlib import Path

import asyncpg
import jsonschema

from ingestion.pipeline import group_statements, parse_source, schema_checker, validate_extraction

SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text()

# Job-id prefix for the *document extraction* path (ingestion.extract.runner). The seed
# pipeline uses "job:" instead, and the concurrency guard below deliberately covers only
# the extraction prefix: a seed run is idempotent, offline and free, so it has no spend to
# protect. ``runner`` imports this constant so the prefix is not written down twice.
EXTRACT_JOB_PREFIX = "ingest:"

# How long a 'running' extraction row may sit before a new run treats it as an orphan and
# takes the source over. It takes a hard kill to leave one behind — runner's finally-block
# closes the job on both the success and the exception path — but do not read that as rare:
# `make up` (docker compose up -d --build) restarts the backend, and a 4-minute extraction
# cannot finish inside docker's 10s stop grace, so it is SIGKILLed mid-run. Restarting the
# backend while an ingest is going is the *likeliest* way to produce one of these.
#
# The value is deliberately generous. Too short is the dangerous direction: it would let a
# still-running extraction be mistaken for an orphan and start a *second* one, which is the
# duplicate token spend this whole change exists to prevent. Too long merely makes the
# operator wait (or clear one DB row by hand).
STALE_AFTER = timedelta(hours=2)

_MIGRATION_ADD_SCHEMA_CHECK = """
ALTER TABLE curation_items ADD COLUMN IF NOT EXISTS schema_check JSONB;
"""

# Groups per-element curation_items into one reviewable proposal (statement).
# NULL = legacy ungrouped item; backward-compatible.
_MIGRATION_ADD_GROUP_ID = """
ALTER TABLE curation_items ADD COLUMN IF NOT EXISTS group_id TEXT;
"""

# At most one *running* extraction per source. This is what makes a retry after nginx's 504
# harmless: the second submission cannot even open a job, so it never reaches the LLM loop.
#
# The unique index (rather than a session advisory lock) is what makes this connection-
# agnostic — whoever submits, from whichever connection or process, is refused.
#
# The UPDATE runs first and is required, not cosmetic: if a previous duplicate-submission
# incident already left two 'running' rows for one source, CREATE UNIQUE INDEX would fail,
# ensure_schema would fail, and the backend would not start. It keeps the newest row per
# source and closes the older ones, which are orphans by definition.
#
# NOTE: the 'ingest:%' literal below must stay in sync with EXTRACT_JOB_PREFIX. It cannot
# reference the constant — an index predicate is stored SQL — so changing the prefix means
# editing this migration and re-creating the index.
_MIGRATION_INGEST_CONCURRENCY_GUARD = """
UPDATE ingestion_jobs AS j
SET status = 'failed',
    error_message = COALESCE(j.error_message, 'orphaned running job closed by concurrency-guard migration'),
    finished_at = COALESCE(j.finished_at, now())
WHERE j.status = 'running'
  AND j.job_id LIKE 'ingest:%'
  AND EXISTS (
      SELECT 1 FROM ingestion_jobs AS newer
      WHERE newer.status = 'running'
        AND newer.job_id LIKE 'ingest:%'
        AND newer.source_path IS NOT DISTINCT FROM j.source_path
        AND (newer.started_at, newer.job_id) > (j.started_at, j.job_id)
  );

CREATE UNIQUE INDEX IF NOT EXISTS ingestion_jobs_one_running_extract_per_source
    ON ingestion_jobs (source_path)
    WHERE status = 'running' AND job_id LIKE 'ingest:%';
"""


class IngestAlreadyRunning(Exception):
    """Raised when an extraction for the same source is already in flight.

    Carries the blocking job's identity so the caller can tell the operator which job to go
    look at, rather than only that "something" is running. Message wording is left to the
    caller: the HTTP layer owns user-facing text, this layer owns facts.
    """

    def __init__(self, source_path: str, job_id: str | None, started_at: datetime | None) -> None:
        super().__init__(f"an extraction for {source_path} is already running (job_id={job_id})")
        self.source_path = source_path
        self.job_id = job_id
        self.started_at = started_at


async def ensure_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(SCHEMA_SQL)
    await conn.execute(_MIGRATION_ADD_SCHEMA_CHECK)
    await conn.execute(_MIGRATION_ADD_GROUP_ID)
    await conn.execute(_MIGRATION_INGEST_CONCURRENCY_GUARD)


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


async def claim_ingest_source(conn: asyncpg.Connection, job_id: str, source_path: str) -> None:
    """Open an extraction job, but only if no other one holds this source.

    The guarded counterpart of :func:`start_ingestion_job`, used by the document extraction
    path. ``POST /admin/ingest/run`` blocks for minutes and exceeds nginx's proxy timeout, so
    the operator sees a 504 for a run that is in fact still going; retrying used to start a
    second extraction alongside the first and pay for the same chapter twice. Refusing the
    claim here — before the caller reaches any LLM call — is what makes that retry harmless.

    Raises :class:`IngestAlreadyRunning` instead of opening a second job.
    """
    # Release orphans first, scoped to this source. A row can only get stuck here if the
    # process was killed outright; anything that merely fails is closed by runner's finally.
    await conn.execute(
        """
        UPDATE ingestion_jobs
        SET status = 'failed',
            error_message = COALESCE(error_message, 'interrupted: still running past the stale threshold'),
            finished_at = COALESCE(finished_at, now())
        WHERE source_path = $1
          AND status = 'running'
          AND job_id LIKE $3
          AND started_at < now() - $2::interval
        """,
        source_path,
        STALE_AFTER,
        EXTRACT_JOB_PREFIX + "%",
    )

    try:
        await conn.execute(
            "INSERT INTO ingestion_jobs (job_id, status, source_path) VALUES ($1, 'running', $2)",
            job_id,
            source_path,
        )
    except asyncpg.UniqueViolationError as exc:
        blocking = await conn.fetchrow(
            """
            SELECT job_id, started_at FROM ingestion_jobs
            WHERE source_path = $1 AND status = 'running' AND job_id LIKE $2
            ORDER BY started_at DESC LIMIT 1
            """,
            source_path,
            EXTRACT_JOB_PREFIX + "%",
        )
        # The row may have finished between the failed INSERT and this lookup, so report what
        # was found rather than asserting it is there.
        raise IngestAlreadyRunning(
            source_path=source_path,
            job_id=blocking["job_id"] if blocking else None,
            started_at=blocking["started_at"] if blocking else None,
        ) from exc


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
    conn: asyncpg.Connection,
    candidate: dict,
    chunk_id: str,
) -> tuple[bool, str | None, int, int, int]:
    """Stage validated nodes/edges as proposed curation items, **grouped by statement**.

    Returns ``(ok, error, staged_nodes, staged_edges, staged_groups)`` where every count is of rows
    *actually* inserted — duplicates hit ``ON CONFLICT DO NOTHING`` and are excluded, so a re-ingest
    honestly reports zeros rather than claiming it queued work it did not.

    Items carry a ``group_id`` so the whole statement is reviewed as one unit; without it the
    extraction path writes rows the group Review queue can never show (it lists only grouped
    items), which is what this staging path used to do.

    A group keeps **every** member of its statement, including concepts already in the approved
    graph. An earlier version filtered those out here, reasoning that a reviewer should not be asked
    to re-approve curated knowledge — but that reasoning applies to what gets *written*, and it is
    already handled where writing happens (``approve_group`` reuses an existing member instead of
    rewriting it). Filtering here protected nothing and removed the very concepts the expert lens
    names, so on a chapter whose concepts were all already curated every group arrived at review
    saying "本提案沒有可呈現的內容" — with the gate passing it, because every gate check reads
    ``nodes`` and an empty list satisfies them all vacuously.

    Put plainly: staging decides what the reviewer reads, approval decides what the graph gets.
    """
    try:
        validate_extraction.validate_extraction_output(candidate)
    except jsonschema.ValidationError as exc:
        return False, str(exc), 0, 0, 0

    staged_nodes = 0
    staged_edges = 0
    staged_groups = 0
    for group in group_statements.split_into_statements(candidate, chunk_id):
        group_id = group["group_id"]
        nodes = group["nodes"]
        edges = group["edges"]
        group_rows = 0
        for node in nodes:
            check = schema_checker.check_node(node)
            row = await conn.fetchrow(
                """
                INSERT INTO curation_items
                    (item_id, item_type, action, payload, status, proposed_by, schema_check, group_id)
                VALUES ($1, 'node', 'create', $2, 'proposed', 'llm', $3, $4)
                ON CONFLICT (item_id) DO NOTHING
                RETURNING item_id
                """,
                f"curation:{group_id}:{node['id']}",
                json.dumps(node),
                json.dumps(check),
                group_id,
            )
            staged_nodes += row is not None
            group_rows += row is not None
        for edge in edges:
            check = schema_checker.check_edge(edge)
            row = await conn.fetchrow(
                """
                INSERT INTO curation_items
                    (item_id, item_type, action, payload, status, proposed_by, schema_check, group_id)
                VALUES ($1, 'edge', 'create', $2, 'proposed', 'llm', $3, $4)
                ON CONFLICT (item_id) DO NOTHING
                RETURNING item_id
                """,
                f"curation:{group_id}:{edge['id']}",
                json.dumps(edge),
                json.dumps(check),
                group_id,
            )
            staged_edges += row is not None
            group_rows += row is not None
        # only count a group as staged if it actually put rows in the queue — a re-ingest inserts
        # nothing and must not report N new statements awaiting review (review finding M3)
        staged_groups += group_rows > 0
    return True, None, staged_nodes, staged_edges, staged_groups


_REVIEW_GROUPS = parse_source.DATA_DIR / "expert_demo" / "review_groups.json"


async def stage_demo_review_group(
    conn: asyncpg.Connection,
    group_id: str,
    candidate: dict,
    possible_schema_gap: bool = False,
) -> tuple[int, int]:
    """Stage one demo proposal group (nodes+edges of a statement) as proposed curation_items.

    All items share ``group_id`` (so the Review page assembles them into one reviewable
    statement), each carries its own ``schema_check``, and item_ids are group-scoped so the
    demo seed never collides with the extraction path. Idempotent (``ON CONFLICT DO NOTHING``).

    ``possible_schema_gap`` is a group-level hint (a genuine schema gap, per D5). We stash it
    in each member's ``schema_check`` JSONB (``group_possible_schema_gap``) so ``list_groups``
    can surface it on the proposal without a new column.
    """

    def _check(item_check: dict) -> str:
        if possible_schema_gap:
            item_check = {**item_check, "group_possible_schema_gap": True}
        return json.dumps(item_check)

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
            _check(schema_checker.check_node(node)),
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
            _check(schema_checker.check_edge(edge)),
            group_id,
        )
        staged_edges += row is not None
    return staged_nodes, staged_edges


async def stage_demo_review_groups(conn: asyncpg.Connection) -> dict:
    """Seed the demo proposal groups (`review_groups.json`) into the review queue.

    These deliberately propose knowledge that is **not** already in the approved seed
    graph, so approving one genuinely adds knowledge and the invariant (invisible before
    approval, retrievable after) is real. Edges may reference existing approved nodes —
    those are referenced, never re-proposed, so approval cannot overwrite curated nodes.
    """
    groups = json.loads(_REVIEW_GROUPS.read_text(encoding="utf-8"))
    # Converge proposed demo state on the JSON: drop ALL still-proposed demo items, then
    # re-stage below. This makes *content* changes to a group take effect (not just group
    # add/remove) — otherwise ON CONFLICT DO NOTHING would keep stale items from a prior seed.
    # Approved demo items (a reviewer's decision) are status != 'proposed', so they are left
    # untouched; `make demo-reset` is the way to undo those.
    await conn.execute(
        "DELETE FROM curation_items WHERE proposed_by = 'demo' AND status = 'proposed'"
    )
    staged: dict = {}
    for g in groups:
        n, e = await stage_demo_review_group(
            conn,
            g["group_id"],
            {"nodes": g.get("nodes", []), "edges": g.get("edges", [])},
            possible_schema_gap=bool(g.get("possible_schema_gap")),
        )
        staged[g["group_id"]] = {"nodes": n, "edges": e}
    return staged
