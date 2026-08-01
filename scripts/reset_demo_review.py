"""Undo demo review-group approvals so the Review demo is fresh again.

Any proposal group approved in the demo (``proposed_by='demo'``) is removed from the
knowledge graph and its curation_items are returned to ``proposed`` (so it re-appears in
the review queue). Real curated knowledge is untouched — only demo-origin items are
affected. Safe to re-run.

Run: ``make demo-reset`` (or ``docker compose run --rm backend python -m scripts.reset_demo_review``).
"""

import asyncio
import json
import os
import uuid

import asyncpg
from neo4j import GraphDatabase


async def _audit_delete(pg: asyncpg.Connection, item_type: str, target_id: str) -> None:
    """Append an append-only audit row for a reset deletion (governance is auditable —
    even the demo-reset utility must leave a trace)."""
    await pg.execute(
        "INSERT INTO graph_change_logs "
        "(change_id, action, target_type, target_id, actor, reason) "
        "VALUES ($1, 'delete', $2, $3, 'demo-reset', 'demo review reset')",
        f"change:{uuid.uuid4()}",
        item_type,
        target_id,
    )


async def reset() -> dict:
    pg = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "biology_graphrag"),
        user=os.getenv("POSTGRES_USER", "biology_app"),
        password=os.getenv("POSTGRES_PASSWORD", "change_me"),
    )
    try:
        rows = await pg.fetch(
            "SELECT item_id, item_type, payload FROM curation_items "
            "WHERE proposed_by = 'demo' AND status = 'approved'"
        )
        deleted = {"nodes": 0, "edges": 0}
        driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
            auth=(os.getenv("NEO4J_USERNAME", "neo4j"), os.getenv("NEO4J_PASSWORD", "change_me")),
        )
        try:
            with driver.session() as session:
                for row in rows:
                    payload = row["payload"]
                    payload = json.loads(payload) if isinstance(payload, str) else payload
                    node_id = payload["id"]
                    if row["item_type"] == "node":
                        session.run("MATCH (n {id: $id}) DETACH DELETE n", id=node_id)
                        deleted["nodes"] += 1
                    else:
                        session.run("MATCH ()-[e {id: $id}]->() DELETE e", id=node_id)
                        deleted["edges"] += 1
                    await _audit_delete(pg, row["item_type"], node_id)
        finally:
            driver.close()

        await pg.execute(
            "UPDATE curation_items SET status = 'proposed', reviewed_by = NULL, "
            "reason = NULL, reviewed_at = NULL "
            "WHERE proposed_by = 'demo' AND status = 'approved'"
        )
        result = {"reset_items": len(rows), "graph_deleted": deleted}
        print(f"demo review reset: {result}")
        return result
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(reset())
