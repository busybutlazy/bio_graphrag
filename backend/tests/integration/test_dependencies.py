import pytest
from app.db.neo4j_client import check_neo4j
from app.db.postgres import check_postgres
from app.db.qdrant_client import check_qdrant


@pytest.mark.asyncio
async def test_postgres_reachable():
    ok, detail = await check_postgres()
    assert ok, detail


@pytest.mark.asyncio
async def test_neo4j_reachable():
    ok, detail = await check_neo4j()
    assert ok, detail


def test_qdrant_reachable():
    ok, detail = check_qdrant()
    assert ok, detail
