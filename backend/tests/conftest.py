import asyncio

import asyncpg
import pytest

from app.core.config import settings
from ingestion.pipeline import load_postgres


async def _ensure_schema() -> None:
    conn = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )
    try:
        await load_postgres.ensure_schema(conn)
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def ensure_postgres_schema():
    """Create the Postgres schema before any test runs.

    Several integration tests hit curation/query tables directly without going
    through the ingestion pipeline first. Without this, a fresh Postgres volume
    (no prior `make seed-sample`) would fail those tests with UndefinedTableError.
    """
    asyncio.run(_ensure_schema())
    yield
