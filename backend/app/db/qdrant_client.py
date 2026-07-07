from qdrant_client import QdrantClient

from app.core.config import settings

COLLECTION_NAME = "biology_chunks"


def check_qdrant() -> tuple[bool, str | None]:
    try:
        client = QdrantClient(url=settings.qdrant_url, timeout=5)
        client.get_collections()
        return True, None
    except Exception as exc:
        return False, str(exc)


def search_chunks(query_vector: list[float], top_k: int) -> list[dict]:
    """Return the top_k nearest chunk payloads with their similarity score."""
    client = QdrantClient(url=settings.qdrant_url, timeout=5)
    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    )
    hits = []
    for point in result.points:
        payload = point.payload or {}
        hits.append(
            {
                "chunk_id": payload.get("chunk_id"),
                "doc_id": payload.get("doc_id"),
                "concept_ids": payload.get("concept_ids", []),
                "score": point.score,
            }
        )
    return hits
