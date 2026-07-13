"""Hybrid retrieval orchestration (Phase 3).

question
  -> vector search top_k chunks
  -> collect concept_ids from hits
  -> Neo4j expand approved subgraph (depth-limited, node-capped)
  -> compose grounded context
  -> LLM answer
"""

import anyio

from app.core.config import settings
from app.db.neo4j_driver import get_driver
from app.graph.cypher_templates import expand_from_seeds
from app.llm import gateway
from app.llm.usage import UsageAccumulator
from app.rag import context_composer, retriever_vector

# Hard cap on nodes returned from a single retrieval (docs/api_contract.md).
MAX_RETURNED_NODES = 30


def _debug_allowed() -> bool:
    return settings.app_env in {"local", "dev", "test"}


async def retrieve(
    question: str, top_k: int, graph_depth: int, acc: UsageAccumulator | None = None
) -> dict:
    """Run vector + graph retrieval and compose context. No LLM answer here.

    Embedding tokens spent are added to ``acc`` when provided.
    """
    chunk_hits = await retriever_vector.retrieve(question, top_k, acc)

    seed_ids: list[str] = []
    seen: set[str] = set()
    for hit in chunk_hits:
        for cid in hit.get("concept_ids", []):
            if cid not in seen:
                seen.add(cid)
                seed_ids.append(cid)

    subgraph = await anyio.to_thread.run_sync(
        expand_from_seeds, get_driver(), seed_ids, graph_depth, MAX_RETURNED_NODES
    )
    composed = context_composer.compose(chunk_hits, subgraph)
    composed["vector_hits"] = len(chunk_hits)
    composed["graph_depth"] = graph_depth
    return composed


async def answer_query(
    question: str,
    top_k: int,
    graph_depth: int,
    include_debug: bool,
    acc: UsageAccumulator | None = None,
) -> dict:
    acc = acc if acc is not None else UsageAccumulator()
    composed = await retrieve(question, top_k, graph_depth, acc)
    answer, answer_usage = await anyio.to_thread.run_sync(
        gateway.generate_answer, composed["context_text"], question
    )
    acc.add(answer_usage)

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
