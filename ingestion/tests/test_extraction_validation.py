import pytest

from ingestion.pipeline import load_postgres

CHUNK = "chunk:sample:001"


@pytest.mark.asyncio
async def test_invalid_extraction_output_is_rejected_and_not_staged(pg_conn):
    candidate = {"nodes": [{"type": "Hormone"}], "edges": []}  # missing required fields

    before_count = await pg_conn.fetchval("SELECT count(*) FROM curation_items")
    (
        ok,
        error,
        staged_nodes,
        staged_edges,
        staged_groups,
    ) = await load_postgres.stage_extraction_output(pg_conn, candidate, CHUNK)
    after_count = await pg_conn.fetchval("SELECT count(*) FROM curation_items")

    assert ok is False
    assert error is not None
    assert (staged_nodes, staged_edges, staged_groups) == (0, 0, 0)
    assert after_count == before_count


@pytest.mark.asyncio
async def test_valid_extraction_output_is_staged_as_proposed(pg_conn):
    candidate = {
        "nodes": [
            {
                "id": "hormone:test_sample_hormone",
                "type": "Hormone",
                "label": "Test Hormone",
                "description": "test",
                "source_chunk_id": CHUNK,
            }
        ],
        "edges": [],
    }

    try:
        (
            ok,
            error,
            staged_nodes,
            staged_edges,
            staged_groups,
        ) = await load_postgres.stage_extraction_output(pg_conn, candidate, CHUNK)

        assert ok is True
        assert error is None
        # a lone concept anchors no pattern, so it lands in the chunk's residual statement
        assert (staged_nodes, staged_edges, staged_groups) == (1, 0, 1)

        row = await pg_conn.fetchrow(
            "SELECT status, item_type, proposed_by, group_id FROM curation_items "
            "WHERE payload->>'id' = $1",
            "hormone:test_sample_hormone",
        )
        assert row is not None
        assert row["status"] == "proposed"
        assert row["item_type"] == "node"
        assert row["proposed_by"] == "llm"
        assert row["group_id"] == f"group:llm:{CHUNK}:residual"
    finally:
        await pg_conn.execute("DELETE FROM curation_items WHERE proposed_by = 'llm'")
