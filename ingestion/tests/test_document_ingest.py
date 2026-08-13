import os
from datetime import timedelta

import asyncpg
import pytest

from ingestion.extract import runner
from ingestion.pipeline import load_postgres

CHAPTER = (
    "---\n"
    "doc_id: doc:test_sample:ingest\n"
    "title: 測試章節\n"
    "topic: blood_glucose_regulation\n"
    "grade_level: 高二\n"
    "source_type: test\n"
    "---\n"
    "# 血糖調節\n"
    "當血糖上升時,胰島素分泌增加,促進葡萄糖進入細胞。\n\n"
    "## 升糖素\n"
    "當血糖下降時,升糖素分泌增加,促進肝醣分解。"
)

DOC_ID = "doc:test_sample:ingest"


@pytest.fixture(autouse=True)
def _force_offline_embeddings(monkeypatch):
    """Unit tests must never spend tokens merely because the host has a key."""
    monkeypatch.setenv("OPENAI_API_KEY", "")


def _write_chapter(tmp_path):
    path = tmp_path / "chapter.md"
    path.write_text(CHAPTER, encoding="utf-8")
    return path


def _valid_candidate(chunk_id: str) -> dict:
    return {
        "nodes": [
            {
                "id": "hormone:test_sample_insulin",
                "type": "Hormone",
                "label": "胰島素",
                "description": "降低血糖的激素",
                "source_chunk_id": chunk_id,
            }
        ],
        "edges": [],
    }


@pytest.mark.asyncio
async def test_extract_retry_includes_validation_error():
    prompts = []

    def invalid_extract(system_prompt, user_prompt):
        prompts.append(user_prompt)
        return {"nodes": [{"type": "Hormone"}], "edges": []}, 5

    attempt = await runner._extract_chunk(
        extract_fn=invalid_extract,
        system_prompt="system",
        user_prompt="original",
        retries=1,
    )

    # nothing valid survives salvage either, so this stays a failed chunk
    assert attempt.candidate is None
    assert attempt.tokens == 10
    assert attempt.error and "ValidationError" in attempt.error
    assert [d["kind"] for d in attempt.dropped] == ["node"]
    assert len(prompts) == 2
    assert prompts[0] == "original"
    assert "上一次輸出未通過驗證" in prompts[1]
    assert "ValidationError" in prompts[1]


# --- dry run: no DB, no spend -------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_assembles_prompts_without_db(tmp_path):
    path = _write_chapter(tmp_path)

    report = await runner.ingest_document(
        source_path=path,
        strategy="markdown_header",
        dry_run=True,
    )

    assert report.status == "preview"
    assert report.dry_run is True
    assert report.doc_id == DOC_ID
    assert report.system_prompt and "extraction agent" in report.system_prompt
    assert len(report.chunks) >= 2
    # every previewed chunk carries the assembled user prompt and zero spend
    for ch in report.chunks:
        assert ch.user_prompt and ch.chunk_id in ch.user_prompt
        assert ch.content in ch.user_prompt
        assert ch.tokens == 0
        assert ch.proposed_node_ids == []


@pytest.mark.asyncio
async def test_dry_run_strategy_switch_changes_chunk_count(tmp_path):
    path = _write_chapter(tmp_path)

    coarse = await runner.ingest_document(
        source_path=path,
        strategy="fixed",
        chunk_params={"chunk_size": 1000, "chunk_overlap": 0},
        dry_run=True,
    )
    fine = await runner.ingest_document(
        source_path=path,
        strategy="fixed",
        chunk_params={"chunk_size": 20, "chunk_overlap": 0},
        dry_run=True,
    )
    assert len(fine.chunks) > len(coarse.chunks)
    assert coarse.stats["chunk_params"]["chunk_size"] == 1000


# --- full run: mock extractor, real PG/Qdrant --------------------------------


@pytest.mark.asyncio
async def test_full_run_stages_proposed_and_writes_chunks(tmp_path, pg_conn, qdrant_client):
    path = _write_chapter(tmp_path)

    def fake_extract(system_prompt, user_prompt):
        # derive the chunk id from the prompt so source_chunk_id is coherent
        chunk_id = next(
            line.split("chunk_id:")[1].strip()
            for line in user_prompt.splitlines()
            if line.startswith("chunk_id:")
        )
        return _valid_candidate(chunk_id), 42

    try:
        report = await runner.ingest_document(
            source_path=path,
            strategy="fixed",
            chunk_params={"chunk_size": 40, "chunk_overlap": 10},
            extract_fn=fake_extract,
            pg_conn=pg_conn,
            qdrant=qdrant_client,
            neo4j_driver=None,
        )

        assert report.status == "success"
        assert report.stats["proposed_nodes"] >= 1
        assert report.stats["failed_chunks"] == 0
        assert report.stats["tokens"] == 42 * report.stats["chunks"]

        # chunks persisted and reference the proposed (not-yet-approved) node id
        rows = await pg_conn.fetch("SELECT concept_ids FROM chunks WHERE doc_id = $1", DOC_ID)
        assert len(rows) == report.stats["chunks"]

        # node staged as a proposed curation item, now carrying a group_id so the review queue
        # can actually show it (item_id is group-scoped, so it is no longer `curation:{node_id}`)
        item = await pg_conn.fetchrow(
            "SELECT item_id, status, proposed_by, group_id FROM curation_items "
            "WHERE payload->>'id' = $1",
            "hormone:test_sample_insulin",
        )
        assert item is not None and item["status"] == "proposed" and item["proposed_by"] == "llm"
        assert item["group_id"] is not None
        assert item["item_id"] == f"curation:{item['group_id']}:hormone:test_sample_insulin"
        assert report.stats["proposed_groups"] >= 1
    finally:
        await _cleanup(pg_conn, qdrant_client)


# --- T2: per-group staging (changes/extract-per-group-staging) ----------------


def _statement_candidate(chunk_id: str) -> dict:
    """A complete three-part statement plus an unrelated concept, so one chunk yields both a
    pattern group and a residual group."""
    return {
        "nodes": [
            {
                "id": "hormone:test_stmt_insulin",
                "type": "Hormone",
                "label": "胰島素",
                "description": "d",
                "source_chunk_id": chunk_id,
            },
            {
                "id": "regulatory_effect:test_stmt_lower",
                "type": "RegulatoryEffect",
                "label": "降血糖",
                "description": "d",
                "source_chunk_id": chunk_id,
            },
            {
                "id": "physiological_variable:test_stmt_bg",
                "type": "PhysiologicalVariable",
                "label": "血糖",
                "description": "d",
                "source_chunk_id": chunk_id,
            },
            {
                "id": "misconception:test_stmt_wrong",
                "type": "Misconception",
                "label": "誤解",
                "description": "d",
                "source_chunk_id": chunk_id,
            },
        ],
        "edges": [
            {
                "id": "e:test_stmt:has_effect",
                "type": "HAS_EFFECT",
                "source": "hormone:test_stmt_insulin",
                "target": "regulatory_effect:test_stmt_lower",
                "source_chunk_id": chunk_id,
            },
            {
                "id": "e:test_stmt:on_variable",
                "type": "ON_VARIABLE",
                "source": "regulatory_effect:test_stmt_lower",
                "target": "physiological_variable:test_stmt_bg",
                "source_chunk_id": chunk_id,
            },
            {
                "id": "e:test_stmt:decreases",
                "type": "DECREASES",
                "source": "regulatory_effect:test_stmt_lower",
                "target": "physiological_variable:test_stmt_bg",
                "source_chunk_id": chunk_id,
            },
        ],
    }


def _one_chunk_extractor(candidate_fn=_statement_candidate):
    def fake_extract(system_prompt, user_prompt):
        chunk_id = next(
            line.split("chunk_id:")[1].strip()
            for line in user_prompt.splitlines()
            if line.startswith("chunk_id:")
        )
        return candidate_fn(chunk_id), 1

    return fake_extract


async def _ingest(path, pg_conn, qdrant_client, **kw):
    return await runner.ingest_document(
        source_path=path,
        strategy="fixed",
        chunk_params={"chunk_size": 10_000, "chunk_overlap": 0},  # whole chapter = one chunk
        extract_fn=_one_chunk_extractor(),
        pg_conn=pg_conn,
        qdrant=qdrant_client,
        neo4j_driver=None,
        **kw,
    )


@pytest.mark.asyncio
async def test_extracted_statements_reach_the_group_review_queue(tmp_path, pg_conn, qdrant_client):
    """The point of the change: extraction output becomes reviewable statements, not loose items.

    Imports the API service on purpose — this is the seam the change exists to close, and asserting
    on `curation_items` alone would not prove the queue can see them.
    """
    from app.curation import service

    path = _write_chapter(tmp_path)
    try:
        report = await _ingest(path, pg_conn, qdrant_client)
        assert report.stats["proposed_groups"] == 2  # one statement + one residual

        # scoped to this test's own document: tests share a database, and an unscoped filter picks
        # up whatever another test left staged — the same mistake the teardown was corrected for
        prefix = f"group:llm:{DOC_ID}"
        groups = {
            g["group_id"]: g
            for g in await service.list_groups()
            if g["group_id"].startswith(prefix)
        }
        assert len(groups) == 2

        pattern = next(
            g for k, g in groups.items() if k.endswith("regulatory_effect:test_stmt_lower")
        )
        assert pattern["schema_gate"]["result"] == "pass"
        assert "胰島素" in pattern["understanding"]["text"]
        assert "血糖" in pattern["understanding"]["text"]

        residual = next(g for k, g in groups.items() if k.endswith(":residual"))
        assert [n["id"] for n in residual["proposal"]["proposed_nodes"]] == [
            "misconception:test_stmt_wrong"
        ]
    finally:
        await _cleanup(pg_conn, qdrant_client)


@pytest.mark.asyncio
async def test_re_ingest_does_not_duplicate_the_review_queue(tmp_path, pg_conn, qdrant_client):
    """Group-scoped item_ids only stay idempotent because group_id is derived, not random."""
    path = _write_chapter(tmp_path)
    try:
        await _ingest(path, pg_conn, qdrant_client)
        after_first = await pg_conn.fetchval(
            "SELECT count(*) FROM curation_items WHERE proposed_by = 'llm'"
        )
        groups_first = await pg_conn.fetchval(
            "SELECT count(DISTINCT group_id) FROM curation_items WHERE proposed_by = 'llm'"
        )

        second = await _ingest(path, pg_conn, qdrant_client)

        assert (
            await pg_conn.fetchval("SELECT count(*) FROM curation_items WHERE proposed_by = 'llm'")
            == after_first
        )
        assert (
            await pg_conn.fetchval(
                "SELECT count(DISTINCT group_id) FROM curation_items WHERE proposed_by = 'llm'"
            )
            == groups_first
        )
        # and the second run reports honestly that it inserted nothing new
        assert second.stats["proposed_nodes"] == 0
        assert second.stats["proposed_edges"] == 0
    finally:
        await _cleanup(pg_conn, qdrant_client)


@pytest.mark.asyncio
async def test_a_group_keeps_every_member_so_the_lens_can_describe_it(
    tmp_path, pg_conn, qdrant_client
):
    """Staging keeps concepts that are already curated; approval is where reuse is decided.

    Filtering them out here instead produced groups with no nodes at all on a chapter whose
    concepts were all already approved — and the expert lens, which names a proposal's nodes, told
    the reviewer "本提案沒有可呈現的內容" while the gate passed it, because every gate check reads
    `nodes` and an empty list satisfies them vacuously. The reviewer could approve knowledge the
    system had just said it could not show them.
    """
    path = _write_chapter(tmp_path)
    try:
        report = await _ingest(path, pg_conn, qdrant_client)
        assert report.status == "success"

        staged = {
            r["payload_id"]
            for r in await pg_conn.fetch(
                "SELECT payload->>'id' AS payload_id FROM curation_items "
                "WHERE starts_with(group_id, 'group:llm:' || $1) AND item_type = 'node'",
                DOC_ID,
            )
        }
        assert "hormone:test_stmt_insulin" in staged
        assert "regulatory_effect:test_stmt_lower" in staged

        # and every staged group has at least one node, so none of them can render as empty
        rows = await pg_conn.fetch(
            "SELECT group_id, count(*) FILTER (WHERE item_type = 'node') AS nodes "
            "FROM curation_items WHERE starts_with(group_id, 'group:llm:' || $1) GROUP BY group_id",
            DOC_ID,
        )
        assert rows and all(r["nodes"] > 0 for r in rows), [dict(r) for r in rows]
    finally:
        await _cleanup(pg_conn, qdrant_client)


@pytest.mark.asyncio
async def test_full_run_is_idempotent_on_chunk_count(tmp_path, pg_conn, qdrant_client):
    path = _write_chapter(tmp_path)

    def fake_extract(system_prompt, user_prompt):
        return _valid_candidate("chunk:x"), 0

    try:
        r1 = await runner.ingest_document(
            source_path=path,
            strategy="fixed",
            chunk_params={"chunk_size": 40, "chunk_overlap": 10},
            extract_fn=fake_extract,
            pg_conn=pg_conn,
            qdrant=qdrant_client,
        )
        r2 = await runner.ingest_document(
            source_path=path,
            strategy="fixed",
            chunk_params={"chunk_size": 40, "chunk_overlap": 10},
            extract_fn=fake_extract,
            pg_conn=pg_conn,
            qdrant=qdrant_client,
        )
        count = await pg_conn.fetchval("SELECT count(*) FROM chunks WHERE doc_id = $1", DOC_ID)
        assert count == r1.stats["chunks"] == r2.stats["chunks"]
    finally:
        await _cleanup(pg_conn, qdrant_client)


@pytest.mark.asyncio
async def test_failed_extraction_flags_chunk_but_job_succeeds(tmp_path, pg_conn, qdrant_client):
    path = _write_chapter(tmp_path)

    def bad_extract(system_prompt, user_prompt):
        return {"nodes": [{"type": "Hormone"}], "edges": []}, 5  # missing required fields

    try:
        report = await runner.ingest_document(
            source_path=path,
            strategy="fixed",
            chunk_params={"chunk_size": 1000, "chunk_overlap": 0},
            extract_fn=bad_extract,
            pg_conn=pg_conn,
            qdrant=qdrant_client,
        )
        assert report.status == "success"  # job survives per-chunk extraction failure
        assert report.stats["failed_chunks"] == report.stats["chunks"]
        assert report.stats["proposed_nodes"] == 0
        assert all(ch.extraction_error for ch in report.chunks)
        assert "ValidationError" in report.chunks[0].extraction_error
        assert report.stats["extraction_errors"][0]["chunk_id"] == report.chunks[0].chunk_id
        # chunk still written, with empty concept_ids
        row = await pg_conn.fetchrow("SELECT concept_ids FROM chunks WHERE doc_id = $1", DOC_ID)
        assert row is not None
    finally:
        await _cleanup(pg_conn, qdrant_client)


async def _cleanup(pg_conn, qdrant_client):
    from ingestion.pipeline import load_qdrant

    await pg_conn.execute("DELETE FROM chunks WHERE doc_id = $1", DOC_ID)
    await pg_conn.execute("DELETE FROM documents WHERE doc_id = $1", DOC_ID)
    await pg_conn.execute("DELETE FROM ingestion_jobs WHERE source_path LIKE '%chapter.md'")
    # Staged proposals too: without this they survive the test and pile up in the review queue,
    # and a later run's `ON CONFLICT DO NOTHING` silently stages nothing — which is how a run
    # counting inserted rows ends up asserting zero.
    # Scoped to this test's own document (review finding M4): tests share the app's Postgres, so an
    # unscoped delete would wipe real proposals waiting for an expert — the review queue is the
    # asset this whole project is about, and a teardown has no business reaching it.
    # starts_with, not LIKE: DOC_ID contains an underscore, which LIKE would read as a wildcard
    # and quietly widen the delete beyond this test's own rows.
    await pg_conn.execute(
        "DELETE FROM curation_items WHERE starts_with(group_id, 'group:llm:' || $1)", DOC_ID
    )
    load_qdrant.delete_chunks_for_doc(qdrant_client, DOC_ID)


def _statement_missing_direction(chunk_id: str) -> dict:
    """The observed failure: the triple arrives with its direction edge malformed (no ``id``)."""
    candidate = _statement_candidate(chunk_id)
    candidate["edges"] = [e for e in candidate["edges"] if not e["id"].endswith(":decreases")] + [
        {
            "type": "DECREASES",
            "source": "regulatory_effect:test_stmt_lower",
            "target": "physiological_variable:test_stmt_bg",
            "source_chunk_id": chunk_id,
        }
    ]
    return candidate


@pytest.mark.asyncio
async def test_a_re_run_supplies_what_salvage_had_to_drop(tmp_path, pg_conn, qdrant_client):
    """Salvage must not be a one-way loss: fixing the extraction and re-running has to complete
    the statement in place.

    Group ids are derived from chunk + anchor, so the repaired edge joins the group the first run
    already created rather than opening a second one. Without that, a dropped element would be
    unrecoverable short of purging the queue by hand.
    """
    from app.curation import service

    path = _write_chapter(tmp_path)
    prefix = f"group:llm:{DOC_ID}"
    try:
        broken = await runner.ingest_document(
            source_path=path,
            strategy="fixed",
            chunk_params={"chunk_size": 10_000, "chunk_overlap": 0},
            extract_fn=_one_chunk_extractor(_statement_missing_direction),
            pg_conn=pg_conn,
            qdrant=qdrant_client,
            neo4j_driver=None,
        )
        # the chunk survived: only the malformed edge was dropped, and it said so
        assert broken.stats["failed_chunks"] == 0
        assert broken.stats["dropped_edges"] == 1
        assert broken.stats["degraded_chunks"] == 0
        assert broken.stats["dropped"][0]["kind"] == "edge"

        groups = {g["group_id"]: g for g in await service.list_groups()}
        anchor = next(g for k, g in groups.items() if k.startswith(prefix) and k.endswith("lower"))
        assert anchor["schema_gate"]["result"] == "fail_pattern", (
            "少了方向邊的陳述必須被 gate 擋下,而不是悄悄通過"
        )

        # re-run with the corrected extraction
        repaired = await _ingest(path, pg_conn, qdrant_client)
        assert repaired.stats["dropped_edges"] == 0

        groups = {g["group_id"]: g for g in await service.list_groups()}
        same_anchor = groups[anchor["group_id"]]
        assert any(e["type"] == "DECREASES" for e in same_anchor["proposal"]["proposed_edges"])
        assert same_anchor["schema_gate"]["result"] == "pass"
    finally:
        await _cleanup(pg_conn, qdrant_client)


# --- T1/T2: same-source concurrency guard (changes/ingest-concurrency-guard) ---
#
# Why these tests open a *second* connection: the guard has to hold no matter who submits.
# Driving both claims down one connection would prove nothing about the case that actually
# cost money — an operator retrying in a new request, which FastAPI serves on a fresh
# connection. A single-connection test would also pass against a session advisory lock,
# which is re-entrant and would not have stopped the incident.


async def _second_connection():
    return await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "biology_graphrag"),
        user=os.getenv("POSTGRES_USER", "biology_app"),
        password=os.getenv("POSTGRES_PASSWORD", "change_me"),
    )


async def _clear_jobs(conn, *source_paths):
    await conn.execute(
        "DELETE FROM ingestion_jobs WHERE source_path = ANY($1::text[])", list(source_paths)
    )


@pytest.mark.asyncio
async def test_claim_refuses_a_second_extraction_of_the_same_source(pg_conn):
    """The incident, reproduced: a retry while the first run is still going."""
    source = "/tmp/guard/chapter-a.md"
    other = await _second_connection()
    try:
        await load_postgres.claim_ingest_source(pg_conn, "ingest:first", source)

        with pytest.raises(load_postgres.IngestAlreadyRunning) as caught:
            await load_postgres.claim_ingest_source(other, "ingest:second", source)

        # names the blocking job, so the operator can go check it instead of guessing
        assert caught.value.job_id == "ingest:first"
        assert caught.value.started_at is not None

        rows = await pg_conn.fetchval(
            "SELECT count(*) FROM ingestion_jobs WHERE source_path = $1", source
        )
        assert rows == 1, "被拒絕的提交不得留下第二列 job"
    finally:
        await _clear_jobs(pg_conn, source)
        await other.close()


@pytest.mark.asyncio
async def test_claim_allows_a_different_source(pg_conn):
    """Two different chapters are two different jobs, not a duplicate."""
    a, b = "/tmp/guard/chapter-a.md", "/tmp/guard/chapter-b.md"
    other = await _second_connection()
    try:
        await load_postgres.claim_ingest_source(pg_conn, "ingest:a", a)
        await load_postgres.claim_ingest_source(other, "ingest:b", b)  # must not raise

        assert (
            await pg_conn.fetchval(
                "SELECT count(*) FROM ingestion_jobs WHERE status = 'running' AND source_path = ANY($1::text[])",
                [a, b],
            )
            == 2
        )
    finally:
        await _clear_jobs(pg_conn, a, b)
        await other.close()


@pytest.mark.asyncio
async def test_claim_reuses_the_source_once_the_job_is_finished(pg_conn):
    """Both terminal states release the source — a failed run must not lock a chapter out."""
    source = "/tmp/guard/chapter-a.md"
    try:
        for job_id, status in (("ingest:ok", "success"), ("ingest:bad", "failed")):
            await load_postgres.claim_ingest_source(pg_conn, job_id, source)
            await load_postgres.finish_ingestion_job(pg_conn, job_id, status, {}, None)

        await load_postgres.claim_ingest_source(pg_conn, "ingest:third", source)  # must not raise
    finally:
        await _clear_jobs(pg_conn, source)


@pytest.mark.asyncio
async def test_claim_takes_over_a_stale_orphan(pg_conn):
    """A hard kill leaves a 'running' row behind; without this the chapter is locked forever."""
    source = "/tmp/guard/chapter-a.md"
    try:
        await pg_conn.execute(
            """
            INSERT INTO ingestion_jobs (job_id, status, source_path, started_at)
            VALUES ('ingest:orphan', 'running', $1, now() - $2::interval)
            """,
            source,
            load_postgres.STALE_AFTER + timedelta(minutes=1),
        )

        await load_postgres.claim_ingest_source(pg_conn, "ingest:takeover", source)

        orphan = await pg_conn.fetchrow(
            "SELECT status, error_message, finished_at FROM ingestion_jobs WHERE job_id = 'ingest:orphan'"
        )
        assert orphan["status"] == "failed"
        assert orphan["error_message"], "孤兒列必須留下可辨識的原因,否則稽核紀錄說謊"
        assert orphan["finished_at"] is not None
    finally:
        await _clear_jobs(pg_conn, source)


@pytest.mark.asyncio
async def test_a_job_just_short_of_stale_still_blocks(pg_conn):
    """The dangerous direction is releasing too early: that is what pays twice."""
    source = "/tmp/guard/chapter-a.md"
    try:
        await pg_conn.execute(
            """
            INSERT INTO ingestion_jobs (job_id, status, source_path, started_at)
            VALUES ('ingest:still-going', 'running', $1, now() - $2::interval)
            """,
            source,
            load_postgres.STALE_AFTER - timedelta(minutes=1),
        )

        with pytest.raises(load_postgres.IngestAlreadyRunning):
            await load_postgres.claim_ingest_source(pg_conn, "ingest:retry", source)
    finally:
        await _clear_jobs(pg_conn, source)


@pytest.mark.asyncio
async def test_the_seed_pipeline_is_not_covered_by_the_guard(pg_conn):
    """Seeding is idempotent, offline and free — it has no spend to protect, and breaking
    `make seed` to guard it would be a strictly worse trade."""
    source = "/app/data/sample"
    try:
        await load_postgres.start_ingestion_job(pg_conn, "job:seed-one", source)
        await load_postgres.start_ingestion_job(pg_conn, "job:seed-two", source)  # must not raise
    finally:
        await pg_conn.execute(
            "DELETE FROM ingestion_jobs WHERE job_id = ANY($1::text[])",
            ["job:seed-one", "job:seed-two"],
        )


@pytest.mark.asyncio
async def test_a_second_ingest_of_the_same_source_spends_nothing(tmp_path, pg_conn, qdrant_client):
    """The whole point: the refusal lands *before* the LLM loop, so a retry costs zero tokens."""
    path = _write_chapter(tmp_path)
    calls = []

    def counting_extract(system_prompt, user_prompt):
        calls.append(user_prompt)
        return _statement_candidate("chunk:x"), 1

    other = await _second_connection()
    try:
        # stand in for the first run, still in flight
        await load_postgres.claim_ingest_source(pg_conn, "ingest:in-flight", str(path))

        with pytest.raises(load_postgres.IngestAlreadyRunning):
            await runner.ingest_document(
                source_path=path,
                strategy="fixed",
                chunk_params={"chunk_size": 10_000, "chunk_overlap": 0},
                extract_fn=counting_extract,
                pg_conn=other,
                qdrant=qdrant_client,
                neo4j_driver=None,
            )

        assert calls == [], "被拒絕的匯入不得呼叫模型——這正是重複扣款的來源"
        assert (
            await pg_conn.fetchval(
                "SELECT count(*) FROM ingestion_jobs WHERE source_path = $1", str(path)
            )
            == 1
        )
    finally:
        await _clear_jobs(pg_conn, str(path))
        await other.close()


@pytest.mark.asyncio
async def test_preview_is_never_blocked(tmp_path, pg_conn, qdrant_client):
    """Preview spends nothing and writes nothing, so it has no reason to queue behind a run —
    and an interviewer exploring the UI must not be blocked by the owner's ingest."""
    path = _write_chapter(tmp_path)
    try:
        await load_postgres.claim_ingest_source(pg_conn, "ingest:in-flight", str(path))

        report = await runner.ingest_document(
            source_path=path,
            strategy="fixed",
            chunk_params={"chunk_size": 10_000, "chunk_overlap": 0},
            dry_run=True,
            neo4j_driver=None,
        )
        assert report.status == "preview"
        assert (
            await pg_conn.fetchval(
                "SELECT count(*) FROM ingestion_jobs WHERE source_path = $1", str(path)
            )
            == 1
        ), "dry run 不得建立 job 列"
    finally:
        await _clear_jobs(pg_conn, str(path))
