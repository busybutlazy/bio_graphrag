import os

import asyncpg
import pytest
import pytest_asyncio
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

from ingestion.pipeline import load_postgres


@pytest_asyncio.fixture
async def pg_conn():
    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "biology_graphrag"),
        user=os.getenv("POSTGRES_USER", "biology_app"),
        password=os.getenv("POSTGRES_PASSWORD", "change_me"),
    )
    await load_postgres.ensure_schema(conn)
    yield conn
    await conn.execute("DELETE FROM curation_items WHERE item_id LIKE '%test_sample%'")
    await conn.close()


@pytest.fixture
def neo4j_driver():
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
        auth=(os.getenv("NEO4J_USERNAME", "neo4j"), os.getenv("NEO4J_PASSWORD", "change_me")),
    )
    yield driver
    driver.close()


@pytest.fixture
def qdrant_client():
    return QdrantClient(url=os.getenv("QDRANT_URL", "http://qdrant:6333"))
