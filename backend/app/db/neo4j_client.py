from neo4j import AsyncGraphDatabase

from app.core.config import settings


async def check_neo4j() -> tuple[bool, str | None]:
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    try:
        async with driver.session() as session:
            await session.run("RETURN 1")
        return True, None
    except Exception as exc:
        return False, str(exc)
    finally:
        await driver.close()
