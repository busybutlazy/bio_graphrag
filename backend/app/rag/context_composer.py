"""Compose grounded context from retrieved chunks and the expanded subgraph.

Produces the pieces the answer generator and QueryResponse need: a single context
string for the LLM, plus deduplicated supporting nodes, relationships, and citations.
"""

SNIPPET_MAX_LEN = 200


def compose(chunk_hits: list[dict], subgraph: dict) -> dict:
    nodes = subgraph.get("nodes", [])
    edges = subgraph.get("edges", [])
    label_by_id = {n["id"]: n["label"] for n in nodes}

    citations = [
        {
            "chunk_id": hit["chunk_id"],
            "doc_id": hit["doc_id"],
            "snippet": hit["content"][:SNIPPET_MAX_LEN],
        }
        for hit in chunk_hits
    ]

    chunk_block = "\n".join(f"- {hit['content']}" for hit in chunk_hits)
    triple_block = "\n".join(
        f"- {label_by_id.get(e['source'], e['source'])} "
        f"--{e['relation']}--> {label_by_id.get(e['target'], e['target'])}"
        for e in edges
    )

    sections = []
    if chunk_block:
        sections.append("相關教材片段:\n" + chunk_block)
    if triple_block:
        sections.append("相關知識圖譜關係:\n" + triple_block)
    context_text = "\n\n".join(sections)

    return {
        "context_text": context_text,
        "supporting_nodes": nodes,
        "relationships_used": edges,
        "citations": citations,
    }
