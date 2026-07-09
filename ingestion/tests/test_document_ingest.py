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


def _write_chapter(tmp_path):
    path = tmp_path / "chapter.md"
    path.write_text(CHAPTER, encoding="utf-8")
    return path


def _valid_candidate(chunk_id: str) -> dict:
    return {
        "nodes": [{
            "id": "hormone:test_sample_insulin",
            "type": "Hormone",
            "label": "胰島素",
            "description": "降低血糖的激素",
            "source_chunk_id": chunk_id,
        }],
        "edges": [],
    }


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
        source_path=path, strategy="fixed",
        chunk_params={"chunk_size": 1000, "chunk_overlap": 0}, dry_run=True,
    )
    fine = await runner.ingest_document(
        source_path=path, strategy="fixed",
        chunk_params={"chunk_size": 20, "chunk_overlap": 0}, dry_run=True,
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

        # node staged as a proposed curation item
        item = await pg_conn.fetchrow(
            "SELECT status, proposed_by FROM curation_items WHERE item_id = $1",
            "curation:hormone:test_sample_insulin",
        )
        assert item is not None and item["status"] == "proposed" and item["proposed_by"] == "llm"
    finally:
        await _cleanup(pg_conn, qdrant_client)


@pytest.mark.asyncio
async def test_full_run_is_idempotent_on_chunk_count(tmp_path, pg_conn, qdrant_client):
    path = _write_chapter(tmp_path)

    def fake_extract(system_prompt, user_prompt):
        return _valid_candidate("chunk:x"), 0

    try:
        r1 = await runner.ingest_document(
            source_path=path, strategy="fixed",
            chunk_params={"chunk_size": 40, "chunk_overlap": 10},
            extract_fn=fake_extract, pg_conn=pg_conn, qdrant=qdrant_client,
        )
        r2 = await runner.ingest_document(
            source_path=path, strategy="fixed",
            chunk_params={"chunk_size": 40, "chunk_overlap": 10},
            extract_fn=fake_extract, pg_conn=pg_conn, qdrant=qdrant_client,
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
            source_path=path, strategy="fixed",
            chunk_params={"chunk_size": 1000, "chunk_overlap": 0},
            extract_fn=bad_extract, pg_conn=pg_conn, qdrant=qdrant_client,
        )
        assert report.status == "success"  # job survives per-chunk extraction failure
        assert report.stats["failed_chunks"] == report.stats["chunks"]
        assert report.stats["proposed_nodes"] == 0
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
    load_qdrant.delete_chunks_for_doc(qdrant_client, DOC_ID)
