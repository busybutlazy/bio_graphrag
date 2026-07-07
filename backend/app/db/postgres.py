import asyncpg

from app.core.config import settings


async def check_postgres() -> tuple[bool, str | None]:
    try:
        conn = await asyncpg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
            timeout=5,
        )
        try:
            await conn.execute("SELECT 1")
        finally:
            await conn.close()
        return True, None
    except Exception as exc:
        return False, str(exc)
