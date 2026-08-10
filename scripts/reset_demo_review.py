"""Undo demo review-group dispositions so the Review demo is fresh again.

Any proposal group approved in the demo (``proposed_by='demo'``) is removed from the
knowledge graph and its curation_items are returned to ``proposed`` (so it re-appears in
the review queue). Groups recorded as a **schema gap** are re-armed the same way — there is
no graph write to undo, only the status. Real curated knowledge is untouched — only
demo-origin items are affected. Safe to re-run.

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


async def _reset_schema_gaps(pg: asyncpg.Connection) -> int:
    """Return demo groups recorded as a schema gap to ``proposed``.

    Nothing was written to Neo4j when the gap was recorded, so only the status is undone —
    but the reset itself is still audited (one row per group), so the append-only log keeps
    both the original ``schema_gap`` decision and its reversal.

    The SELECT and the UPDATE carry the **same** predicate on purpose (review finding L4): an item
    the SELECT skips must not be silently reset by the UPDATE, or it would change state with no
    audit row. Today `record_group_gap` only ever acts on grouped items, so the `group_id IS NOT
    NULL` clause is a no-op — it is here so a future ungrouped `schema_gap` cannot slip through
    unaudited.
    """
    where = "proposed_by = 'demo' AND status = 'schema_gap' AND group_id IS NOT NULL"
    group_ids = [
        r["group_id"]
        for r in await pg.fetch(f"SELECT DISTINCT group_id FROM curation_items WHERE {where}")
    ]
    for group_id in group_ids:
        await pg.execute(
            "INSERT INTO graph_change_logs "
            "(change_id, action, target_type, target_id, actor, reason) "
            "VALUES ($1, 'reset', 'proposal_group', $2, 'demo-reset', "
            "'demo review reset: schema_gap -> proposed')",
            f"change:{uuid.uuid4()}",
            group_id,
        )
    await pg.execute(
        "UPDATE curation_items SET status = 'proposed', reviewed_by = NULL, "
        f"reason = NULL, reviewed_at = NULL WHERE {where}"
    )
    return len(group_ids)


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

        # Graph deletes run FIRST, outside the Postgres transaction (review finding R2). Neo4j
        # cannot join a PG transaction, so if the two were interleaved a later rollback would
        # discard the audit rows for deletions that had already happened — a graph mutated with no
        # trace, the one shape an append-only audit log must never produce. Deleting first means
        # the worst case is the opposite and harmless: deletions recorded, statuses not yet reset,
        # fixed by re-running (the deletes are idempotent).
        deleted = {"nodes": 0, "edges": 0}
        deleted_items: list[tuple[str, str]] = []
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
                    deleted_items.append((row["item_type"], node_id))
        finally:
            driver.close()

        # One transaction for the whole Postgres side (review finding L4): the audit rows for the
        # deletions above and the status resets commit together or not at all.
        async with pg.transaction():
            for item_type, node_id in deleted_items:
                await _audit_delete(pg, item_type, node_id)
            await pg.execute(
                "UPDATE curation_items SET status = 'proposed', reviewed_by = NULL, "
                "reason = NULL, reviewed_at = NULL "
                "WHERE proposed_by = 'demo' AND status = 'approved'"
            )
            gap_groups = await _reset_schema_gaps(pg)
        result = {
            "reset_items": len(rows),
            "graph_deleted": deleted,
            "reset_schema_gap_groups": gap_groups,
        }
        print(f"demo review reset: {result}")
        return result
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(reset())
