import asyncio
import os
import uuid

import asyncpg
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

from ingestion.pipeline import (
    build_chunks,
    build_graph,
    embed_chunks,
    load_neo4j,
    load_postgres,
    load_qdrant,
    parse_source,
)


async def run() -> dict:
    # `change_me` defaults are placeholders for the local Docker demo; override
    # every credential via environment variables in any exposed deployment.
    job_id = f"job:{uuid.uuid4()}"
    stats: dict = {}
    status = "running"
    error_message = None

    pg_conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "biology_graphrag"),
        user=os.getenv("POSTGRES_USER", "biology_app"),
        password=os.getenv("POSTGRES_PASSWORD", "change_me"),
    )
    try:
        await load_postgres.ensure_schema(pg_conn)
        await load_postgres.start_ingestion_job(pg_conn, job_id, str(parse_source.DATA_DIR))

        nodes, edges = parse_source.load_graph_source()
        documents, chunks = parse_source.load_chunk_source()

        nodes, edges = build_graph.build(nodes, edges)
        chunks = build_chunks.build(chunks, nodes)

        embeddings = embed_chunks.embed_chunks(chunks)

        neo4j_driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
            auth=(os.getenv("NEO4J_USERNAME", "neo4j"), os.getenv("NEO4J_PASSWORD", "change_me")),
        )
        try:
            node_count, edge_count = load_neo4j.load(neo4j_driver, nodes, edges)
        finally:
            neo4j_driver.close()

        qdrant_client = QdrantClient(url=os.getenv("QDRANT_URL", "http://qdrant:6333"))
        chunk_count = load_qdrant.load_chunks(qdrant_client, chunks, embeddings)

        await load_postgres.upsert_documents(pg_conn, documents)
        await load_postgres.upsert_chunks(pg_conn, chunks)

        # Seed demo proposal groups (genuinely new knowledge) into the review queue.
        # Idempotent.
        demo_groups = await load_postgres.stage_demo_review_groups(pg_conn)

        stats = {
            "nodes": node_count,
            "edges": edge_count,
            "documents": len(documents),
            "chunks": chunk_count,
            "demo_review_groups": demo_groups,
        }
        status = "success"
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
        raise
    finally:
        await load_postgres.finish_ingestion_job(pg_conn, job_id, status, stats, error_message)
        await pg_conn.close()

    return {"job_id": job_id, "status": status, "stats": stats}


def main() -> None:
    result = asyncio.run(run())
    print(result)


if __name__ == "__main__":
    main()
