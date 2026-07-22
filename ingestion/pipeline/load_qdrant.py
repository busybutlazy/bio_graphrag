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


def collection_name_for_dim(dim: int) -> str:
    """Keep the original offline collection while isolating other dimensions.

    The deterministic offline embedder uses 128 dimensions. OpenAI's
    text-embedding-3-small uses 1536, and Qdrant collections have a fixed vector
    size. Dimension-specific collections let a deployment switch modes without
    deleting or corrupting the existing demo collection.
    """
    return COLLECTION_NAME if dim == 128 else f"{COLLECTION_NAME}_{dim}"


def _point_id(chunk_id: str) -> int:
    return int(hashlib.sha256(chunk_id.encode("utf-8")).hexdigest()[:16], 16)


def ensure_collection(client: QdrantClient, dim: int) -> None:
    collection_name = collection_name_for_dim(dim)
    existing = {c.name for c in client.get_collections().collections}
    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def delete_chunks_for_doc(client: QdrantClient, doc_id: str, dim: int | None = None) -> None:
    """Drop a document's existing points before a re-ingest (mirrors the PG side).

    No-op when the collection does not exist yet (first ingest).
    """
    existing = {c.name for c in client.get_collections().collections}
    targets = (
        [collection_name_for_dim(dim)]
        if dim is not None
        else [
            name
            for name in existing
            if name == COLLECTION_NAME or name.startswith(f"{COLLECTION_NAME}_")
        ]
    )
    for collection_name in targets:
        if collection_name in existing:
            client.delete(
                collection_name=collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                    )
                ),
            )


def load_chunks(
    client: QdrantClient, chunks: list[dict], embeddings: dict[str, list[float]]
) -> int:
    if not chunks:
        return 0

    dim = len(next(iter(embeddings.values())))
    ensure_collection(client, dim=dim)
    collection_name = collection_name_for_dim(dim)
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
    client.upsert(collection_name=collection_name, points=points)
    return len(points)
