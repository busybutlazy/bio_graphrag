"""Vector retrieval stage of the hybrid pipeline.

With a real embedding model (OpenAI) we embed the question and query Qdrant.
Without one, ingestion used deterministic hash embeddings, so cosine similarity
carries no meaning — we fall back to lexical bigram matching over Postgres so the
local demo still returns relevant chunks. Either way we return chunk hits carrying
content and concept_ids, which seed graph expansion and citations.
"""

from app.core.config import settings
from app.db import chunks as chunks_db
from app.db.qdrant_client import search_chunks
from app.llm.usage import TokenUsage, UsageAccumulator
from ingestion.pipeline.embed_chunks import embed_text


def _semantic_enabled() -> bool:
    return settings.llm_provider == "openai" and bool(settings.openai_api_key)


async def retrieve(question: str, top_k: int, acc: UsageAccumulator | None = None) -> list[dict]:
    """Return up to top_k chunk hits: {chunk_id, doc_id, content, concept_ids, score}.

    Embedding tokens (semantic mode only) are added to ``acc`` when provided.
    """
    if not _semantic_enabled():
        return await chunks_db.lexical_search(question, top_k)

    query_vector, embed_tokens = embed_text(question)
    if acc is not None:
        acc.add(TokenUsage(embedding=embed_tokens))
    raw_hits = search_chunks(query_vector, top_k)
    contents = await chunks_db.fetch_chunks_by_ids(
        [h["chunk_id"] for h in raw_hits if h["chunk_id"]]
    )
    enriched = []
    for hit in raw_hits:
        stored = contents.get(hit["chunk_id"])
        if stored is None:
            continue
        enriched.append(
            {
                "chunk_id": hit["chunk_id"],
                "doc_id": hit["doc_id"],
                "content": stored["content"],
                "concept_ids": stored["concept_ids"] or hit.get("concept_ids", []),
                "score": hit["score"],
            }
        )
    return enriched
