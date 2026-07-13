import hashlib

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)

COLLECTION_NAME = "biology_chunks"


def _point_id(chunk_id: str) -> int:
    return int(hashlib.sha256(chunk_id.encode("utf-8")).hexdigest()[:16], 16)


def ensure_collection(client: QdrantClient, dim: int) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def delete_chunks_for_doc(client: QdrantClient, doc_id: str) -> None:
    """Drop a document's existing points before a re-ingest (mirrors the PG side).

    No-op when the collection does not exist yet (first ingest).
    """
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        return
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
        ),
    )


def load_chunks(
    client: QdrantClient, chunks: list[dict], embeddings: dict[str, list[float]]
) -> int:
    if not chunks:
        return 0

    ensure_collection(client, dim=len(next(iter(embeddings.values()))))
    points = [
        PointStruct(
            id=_point_id(chunk["chunk_id"]),
            vector=embeddings[chunk["chunk_id"]],
            payload={
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "concept_ids": chunk["concept_ids"],
                "topic": chunk["topic"],
                "grade_level": chunk["grade_level"],
                "source_type": chunk["source_type"],
            },
        )
        for chunk in chunks
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    return len(points)
