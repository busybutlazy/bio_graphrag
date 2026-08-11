import pytest

from ingestion.extract import runner

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

    candidate, tokens, error = await runner._extract_chunk(
        extract_fn=invalid_extract,
        system_prompt="system",
        user_prompt="original",
        retries=1,
    )

    assert candidate is None
    assert tokens == 10
    assert error and "ValidationError" in error
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
