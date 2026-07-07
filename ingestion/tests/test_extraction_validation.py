import pytest

from ingestion.pipeline import load_postgres


@pytest.mark.asyncio
async def test_invalid_extraction_output_is_rejected_and_not_staged(pg_conn):
    candidate = {"nodes": [{"type": "Hormone"}], "edges": []}  # missing required fields

    before_count = await pg_conn.fetchval("SELECT count(*) FROM curation_items")
    ok, error = await load_postgres.stage_extraction_output(pg_conn, candidate)
    after_count = await pg_conn.fetchval("SELECT count(*) FROM curation_items")

    assert ok is False
    assert error is not None
    assert after_count == before_count


@pytest.mark.asyncio
async def test_valid_extraction_output_is_staged_as_proposed(pg_conn):
    candidate = {
        "nodes": [{
            "id": "hormone:test_sample_hormone",
            "type": "Hormone",
            "label": "Test Hormone",
            "description": "test",
            "source_chunk_id": "chunk:sample:001",
        }],
        "edges": [],
    }

    ok, error = await load_postgres.stage_extraction_output(pg_conn, candidate)

    assert ok is True
    assert error is None

    row = await pg_conn.fetchrow(
        "SELECT status, item_type, proposed_by FROM curation_items WHERE item_id = $1",
        "curation:hormone:test_sample_hormone",
    )
    assert row is not None
    assert row["status"] == "proposed"
    assert row["item_type"] == "node"
    assert row["proposed_by"] == "llm"
