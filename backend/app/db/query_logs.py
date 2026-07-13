import json
import uuid

from app.db.pool import connection


async def log_query(question: str, answer: str, retrieval_debug: dict, latency_ms: int) -> None:
    """Best-effort insert into query_logs; never raise into the request path."""
    try:
        async with connection() as conn:
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
