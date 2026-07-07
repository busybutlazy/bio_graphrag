"""Hybrid retrieval orchestration (Phase 3).

question
  -> vector search top_k chunks
  -> collect concept_ids from hits
  -> Neo4j expand approved subgraph (depth-limited, node-capped)
  -> compose grounded context
  -> LLM answer
"""

from app.core.config import settings
from app.db.neo4j_driver import get_driver
from app.graph.cypher_templates import expand_from_seeds
from app.llm import gateway
from app.rag import context_composer
from app.rag import retriever_vector

# Hard cap on nodes returned from a single retrieval (docs/api_contract.md).
MAX_RETURNED_NODES = 30


def _debug_allowed() -> bool:
    return settings.app_env in {"local", "dev", "test"}


async def retrieve(question: str, top_k: int, graph_depth: int) -> dict:
    """Run vector + graph retrieval and compose context. No LLM call here."""
    chunk_hits = await retriever_vector.retrieve(question, top_k)

    seed_ids: list[str] = []
    seen: set[str] = set()
    for hit in chunk_hits:
        for cid in hit.get("concept_ids", []):
            if cid not in seen:
                seen.add(cid)
                seed_ids.append(cid)

    subgraph = expand_from_seeds(get_driver(), seed_ids, graph_depth, MAX_RETURNED_NODES)
    composed = context_composer.compose(chunk_hits, subgraph)
    composed["vector_hits"] = len(chunk_hits)
    composed["graph_depth"] = graph_depth
    return composed


async def answer_query(
    question: str, top_k: int, graph_depth: int, include_debug: bool
) -> dict:
    composed = await retrieve(question, top_k, graph_depth)
    answer = gateway.generate_answer(composed["context_text"], question)

    result = {
        "answer": answer,
        "supporting_nodes": composed["supporting_nodes"],
        "relationships_used": composed["relationships_used"],
        "citations": composed["citations"],
        "retrieval_debug": None,
    }
    if include_debug and _debug_allowed():
        result["retrieval_debug"] = {
            "vector_hits": composed["vector_hits"],
            "graph_nodes": len(composed["supporting_nodes"]),
            "graph_depth": composed["graph_depth"],
        }
    return result
