"""Export current DB state to seed JSON files.

Reads approved nodes/edges from Neo4j and all documents/chunks from Postgres,
then writes them to data/sample/ — the same files make seed-sample reads from.

Usage (services must be running):
    docker compose run --rm backend python -m scripts.export_seed
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import asyncpg
from neo4j import GraphDatabase

_REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = _REPO_ROOT / "data" / "seed"   # gitignored; data/sample/ is the public fallback

_STANDARD_NODE_PROPS = {"id", "label", "status", "description"}
_STANDARD_EDGE_PROPS = {"id", "status"}


def _export_neo4j(driver) -> tuple[list[dict], list[dict]]:
    nodes: list[dict] = []
    edges: list[dict] = []
    with driver.session() as session:
        for record in session.run(
            "MATCH (n) WHERE n.status = 'approved' "
            "RETURN n, labels(n) AS labels ORDER BY n.id"
        ):
            props = dict(record["n"].items())
            extra = {k: v for k, v in props.items() if k not in _STANDARD_NODE_PROPS}
            nodes.append({
                "id": props["id"],
                "type": record["labels"][0],
                "label": props.get("label", ""),
                "status": "approved",
                "description": props.get("description", ""),
                "properties": extra,
            })

        for record in session.run(
            "MATCH (a)-[r]->(b) WHERE r.status = 'approved' "
            "RETURN a.id AS source, b.id AS target, type(r) AS rel_type, r ORDER BY r.id"
        ):
            props = dict(record["r"].items())
            extra = {k: v for k, v in props.items() if k not in _STANDARD_EDGE_PROPS}
            edges.append({
                "id": props.get("id", ""),
                "type": record["rel_type"],
                "source": record["source"],
                "target": record["target"],
                "status": "approved",
                "properties": extra,
            })

    return nodes, edges


async def _export_postgres(conn: asyncpg.Connection) -> tuple[list[dict], list[dict]]:
    doc_rows = await conn.fetch(
        "SELECT doc_id, title, topic, grade_level, source_type FROM documents ORDER BY doc_id"
    )
    documents = [dict(row) for row in doc_rows]

    chunk_rows = await conn.fetch(
        "SELECT chunk_id, doc_id, content, concept_ids, topic, grade_level, source_type "
        "FROM chunks ORDER BY chunk_id"
    )
    chunks = []
    for row in chunk_rows:
        chunk = dict(row)
        concept_ids = chunk["concept_ids"]
        if isinstance(concept_ids, str):
            concept_ids = json.loads(concept_ids)
        chunk["concept_ids"] = list(concept_ids) if concept_ids else []
        chunks.append(chunk)

    return documents, chunks


async def run() -> None:
    neo4j_driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
        auth=(os.getenv("NEO4J_USERNAME", "neo4j"), os.getenv("NEO4J_PASSWORD", "change_me")),
    )
    pg_conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "biology_graphrag"),
        user=os.getenv("POSTGRES_USER", "biology_app"),
        password=os.getenv("POSTGRES_PASSWORD", "change_me"),
    )

    try:
        nodes, edges = _export_neo4j(neo4j_driver)
        documents, chunks = await _export_postgres(pg_conn)
    finally:
        neo4j_driver.close()
        await pg_conn.close()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _write(DATA_DIR / "biology_sample_concepts.json", nodes)
    _write(DATA_DIR / "biology_sample_edges.json", edges)
    _write(DATA_DIR / "biology_sample_documents.json", documents)
    _write(DATA_DIR / "biology_sample_chunks.json", chunks)

    print(f"exported: {len(nodes)} nodes, {len(edges)} edges, "
          f"{len(documents)} documents, {len(chunks)} chunks")
    print(f"→ {DATA_DIR}")


def _write(path: Path, data: list[dict]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
