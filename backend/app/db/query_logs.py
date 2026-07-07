import json
import uuid

import asyncpg

from app.core.config import settings


async def log_query(
    question: str, answer: str, retrieval_debug: dict, latency_ms: int
) -> None:
    """Best-effort insert into query_logs; never raise into the request path."""
    try:
        conn = await asyncpg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
        )
    except Exception:
        return
    try:
        await conn.execute(
            """
            INSERT INTO query_logs (query_id, question, answer, retrieval_debug, latency_ms)
            VALUES ($1, $2, $3, $4, $5)
            """,
            f"query:{uuid.uuid4()}",
            question,
            answer,
            json.dumps(retrieval_debug),
            latency_ms,
        )
    except Exception:
        pass
    finally:
        await conn.close()
