import pytest

from ingestion.pipeline import parse_source, run


@pytest.mark.asyncio
async def test_pipeline_run_loads_expected_counts():
    nodes, edges = parse_source.load_graph_source()
    documents, chunks = parse_source.load_chunk_source()

    result = await run.run()

    assert result["status"] == "success"
    assert result["stats"]["nodes"] == len(nodes)
    assert result["stats"]["edges"] == len(edges)
    assert result["stats"]["documents"] == len(documents)
    assert result["stats"]["chunks"] == len(chunks)


@pytest.mark.asyncio
async def test_pipeline_run_is_idempotent(neo4j_driver, pg_conn):
    nodes, edges = parse_source.load_graph_source()
    documents, chunks = parse_source.load_chunk_source()

    await run.run()
    await run.run()

    with neo4j_driver.session() as session:
        node_count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        edge_count = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    assert node_count == len(nodes)
    assert edge_count == len(edges)

    doc_count = await pg_conn.fetchval("SELECT count(*) FROM documents")
    chunk_count = await pg_conn.fetchval("SELECT count(*) FROM chunks")
    assert doc_count == len(documents)
    assert chunk_count == len(chunks)


@pytest.mark.asyncio
async def test_postgres_metadata_matches_source(pg_conn):
    _, chunks = parse_source.load_chunk_source()
    await run.run()

    sample_chunk = chunks[0]
    row = await pg_conn.fetchrow(
        "SELECT chunk_id, doc_id, content, topic FROM chunks WHERE chunk_id = $1",
        sample_chunk["chunk_id"],
    )
    assert row is not None
    assert row["doc_id"] == sample_chunk["doc_id"]
    assert row["content"] == sample_chunk["content"]
    assert row["topic"] == sample_chunk["topic"]


def test_qdrant_payload_is_queryable(qdrant_client):
    from ingestion.pipeline.load_qdrant import COLLECTION_NAME, _point_id

    _, chunks = parse_source.load_chunk_source()
    sample_chunk = chunks[0]

    points = qdrant_client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[_point_id(sample_chunk["chunk_id"])],
        with_payload=True,
    )
    assert len(points) == 1
    payload = points[0].payload
    assert payload["chunk_id"] == sample_chunk["chunk_id"]
    assert payload["doc_id"] == sample_chunk["doc_id"]
    assert payload["concept_ids"] == sample_chunk["concept_ids"]
