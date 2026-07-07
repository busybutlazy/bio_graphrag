import json

import asyncpg

from app.core.config import settings


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )


def _decode_concept_ids(value) -> list[str]:
    return json.loads(value) if isinstance(value, str) else (value or [])


async def fetch_chunks_by_ids(chunk_ids: list[str]) -> dict[str, dict]:
    """Return {chunk_id: {chunk_id, doc_id, content, concept_ids}} for the ids that exist."""
    if not chunk_ids:
        return {}
    conn = await _connect()
    try:
        rows = await conn.fetch(
            "SELECT chunk_id, doc_id, content, concept_ids FROM chunks WHERE chunk_id = ANY($1)",
            chunk_ids,
        )
    finally:
        await conn.close()
    return {
        row["chunk_id"]: {
            "chunk_id": row["chunk_id"],
            "doc_id": row["doc_id"],
            "content": row["content"],
            "concept_ids": _decode_concept_ids(row["concept_ids"]),
        }
        for row in rows
    }


async def concept_ids_by_topic(topic: str) -> list[str]:
    """Distinct concept_ids referenced by chunks whose topic matches."""
    conn = await _connect()
    try:
        rows = await conn.fetch(
            "SELECT concept_ids FROM chunks WHERE topic = $1", topic
        )
    finally:
        await conn.close()
    seen: dict[str, None] = {}
    for row in rows:
        for cid in _decode_concept_ids(row["concept_ids"]):
            seen.setdefault(cid, None)
    return list(seen)


def _bigrams(text: str) -> set[str]:
    cleaned = "".join(ch for ch in text if ch.isalnum())
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}


async def lexical_search(question: str, top_k: int) -> list[dict]:
    """Offline fallback retrieval: rank chunks by shared character bigrams.

    Used when no real embedding model is configured, so hash-based vectors would
    make Qdrant similarity meaningless. The sample corpus is tiny, so scanning all
    chunks is fine.
    """
    conn = await _connect()
    try:
        rows = await conn.fetch(
            "SELECT chunk_id, doc_id, content, concept_ids FROM chunks"
        )
    finally:
        await conn.close()

    q_bigrams = _bigrams(question)
    scored = []
    for row in rows:
        overlap = len(q_bigrams & _bigrams(row["content"]))
        scored.append(
            (
                overlap,
                {
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "content": row["content"],
                    "concept_ids": _decode_concept_ids(row["concept_ids"]),
                    "score": float(overlap),
                },
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [hit for _, hit in scored[:top_k]]
