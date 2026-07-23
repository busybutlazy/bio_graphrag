import json
import uuid

import anyio
import asyncpg

from app.db.neo4j_driver import get_driver
from app.db.pool import connection
from ingestion.pipeline import load_neo4j
from ingestion.pipeline.normalize_concepts import (
    VALID_NODE_TYPES,
    VALID_RELATIONSHIP_TYPES,
)


class CurationError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def _validate_curation_payload(item_type: str, payload: dict) -> None:
    """Reject payloads that can't be safely written to Neo4j on approval.

    The human create path used to store arbitrary payloads verbatim; a bad
    ``type`` then reached Cypher label interpolation at approval time. Validate
    against the same whitelists the ingestion pipeline uses so illegal types are
    rejected up front (422) instead of failing — or injecting — on approval.
    """
    if item_type not in {"node", "edge"}:
        raise CurationError(422, f"item_type must be 'node' or 'edge', got {item_type!r}")
    if not isinstance(payload, dict) or not payload.get("id"):
        raise CurationError(422, "payload.id is required")
    node_type = payload.get("type")
    allowed = VALID_NODE_TYPES if item_type == "node" else VALID_RELATIONSHIP_TYPES
    if node_type not in allowed:
        raise CurationError(422, f"invalid {item_type} type: {node_type!r}")


def _load_json(value):
    return json.loads(value) if isinstance(value, str) else value


async def _log_change(
    conn: asyncpg.Connection,
    action: str,
    target_type: str,
    target_id: str,
    actor: str,
    reason: str | None,
    curation_item_id: str | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
) -> str:
    change_id = f"change:{uuid.uuid4()}"
    await conn.execute(
        """
        INSERT INTO graph_change_logs
            (change_id, curation_item_id, action, target_type, target_id, actor, reason, before_state, after_state)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        change_id,
        curation_item_id,
        action,
        target_type,
        target_id,
        actor,
        reason,
        json.dumps(before_state) if before_state is not None else None,
        json.dumps(after_state) if after_state is not None else None,
    )
    return change_id


async def record_expert_review(
    case_id: str,
    decision: str,
    schema_gap_type: str | None,
    notes: str | None,
    actor: str,
) -> str:
    """Persist an expert-in-the-loop review as an append-only audit row.

    Reuses the same ``graph_change_logs`` trail as curation / engineer actions, so
    expert-gate decisions are as traceable as any other governance action. Writes
    only an audit row — a demo-case review never touches Neo4j or the approved graph.
    Returns the generated ``change_id``.
    """
    async with connection() as conn:
        return await _log_change(
            conn,
            action="expert_review",
            target_type="expert_demo_case",
            target_id=case_id,
            actor=actor,
            reason=notes,
            after_state={"decision": decision, "schema_gap_type": schema_gap_type},
        )


async def list_items(status: str | None, item_type: str | None) -> list[dict]:
    async with connection() as conn:
        query = "SELECT * FROM curation_items WHERE 1=1"
        params: list[str] = []
        if status:
            params.append(status)
            query += f" AND status = ${len(params)}"
        if item_type:
            params.append(item_type)
            query += f" AND item_type = ${len(params)}"
        query += " ORDER BY created_at DESC"
        rows = await conn.fetch(query, *params)
        return [
            {
                **dict(row),
                "payload": _load_json(row["payload"]),
                "schema_check": _load_json(row["schema_check"]),
            }
            for row in rows
        ]


async def create_item(item_type: str, action: str, payload: dict, reason: str | None) -> str:
    _validate_curation_payload(item_type, payload)
    payload = {**payload, "status": "proposed"}
    item_id = f"curation:{payload['id']}"
    async with connection() as conn:
        await conn.execute(
            """
            INSERT INTO curation_items (item_id, item_type, action, payload, status, proposed_by, reason)
            VALUES ($1, $2, $3, $4, 'proposed', 'human', $5)
            """,
            item_id,
            item_type,
            action,
            json.dumps(payload),
            reason,
        )
    return item_id


async def approve_item(item_id: str, reviewer: str, reason: str | None) -> dict:
    async with connection() as conn:
        row = await conn.fetchrow("SELECT * FROM curation_items WHERE item_id = $1", item_id)
        if row is None:
            raise CurationError(404, f"curation item {item_id} not found")
        if row["status"] != "proposed":
            raise CurationError(409, f"curation item {item_id} is not in proposed state")

        payload = _load_json(row["payload"])
        payload["status"] = "approved"

        driver = get_driver()
        writer = load_neo4j.write_nodes if row["item_type"] == "node" else load_neo4j.write_edges
        await anyio.to_thread.run_sync(writer, driver, [payload])

        await conn.execute(
            """
            UPDATE curation_items SET status = 'approved', reviewed_by = $2, reason = $3, reviewed_at = now()
            WHERE item_id = $1
            """,
            item_id,
            reviewer,
            reason,
        )
        await _log_change(
            conn,
            action="approve",
            target_type=row["item_type"],
            target_id=payload["id"],
            actor=reviewer,
            reason=reason,
            curation_item_id=row["id"],
            after_state=payload,
        )
        return {"item_id": item_id, "status": "approved"}


async def reject_item(item_id: str, reviewer: str, reason: str | None) -> dict:
    async with connection() as conn:
        row = await conn.fetchrow("SELECT * FROM curation_items WHERE item_id = $1", item_id)
        if row is None:
            raise CurationError(404, f"curation item {item_id} not found")
        if row["status"] != "proposed":
            raise CurationError(409, f"curation item {item_id} is not in proposed state")

        payload = _load_json(row["payload"])
        await conn.execute(
            """
            UPDATE curation_items SET status = 'rejected', reviewed_by = $2, reason = $3, reviewed_at = now()
            WHERE item_id = $1
            """,
            item_id,
            reviewer,
            reason,
        )
        await _log_change(
            conn,
            action="reject",
            target_type=row["item_type"],
            target_id=payload["id"],
            actor=reviewer,
            reason=reason,
            curation_item_id=row["id"],
        )
        return {"item_id": item_id, "status": "rejected"}


def _merge_nodes_in_neo4j(source_id: str, target_id: str) -> None:
    driver = get_driver()
    with driver.session() as session:
        present = {
            r["id"]
            for r in session.run(
                "MATCH (n) WHERE n.id IN $ids RETURN n.id AS id",
                ids=[source_id, target_id],
            )
        }
        for node_id in (source_id, target_id):
            if node_id not in present:
                raise CurationError(404, f"node {node_id} not found")

        outgoing = session.run(
            "MATCH (a {id: $source_id})-[r]->(b) WHERE b.id <> $target_id "
            "RETURN type(r) AS type, properties(r) AS props, b.id AS other_id, r.id AS rel_id",
            source_id=source_id,
            target_id=target_id,
        ).data()
        incoming = session.run(
            "MATCH (b)-[r]->(a {id: $source_id}) WHERE b.id <> $target_id "
            "RETURN type(r) AS type, properties(r) AS props, b.id AS other_id, r.id AS rel_id",
            source_id=source_id,
            target_id=target_id,
        ).data()

        for rel in outgoing:
            session.run(
                f"MATCH (t {{id: $target_id}}), (o {{id: $other_id}}) "
                f"MERGE (t)-[r2:{rel['type']} {{id: $rel_id}}]->(o) SET r2 += $props",
                target_id=target_id,
                other_id=rel["other_id"],
                rel_id=rel["rel_id"],
                props=rel["props"],
            )
        for rel in incoming:
            session.run(
                f"MATCH (t {{id: $target_id}}), (o {{id: $other_id}}) "
                f"MERGE (o)-[r2:{rel['type']} {{id: $rel_id}}]->(t) SET r2 += $props",
                target_id=target_id,
                other_id=rel["other_id"],
                rel_id=rel["rel_id"],
                props=rel["props"],
            )

        session.run("MATCH (a {id: $source_id})-[r]-() DELETE r", source_id=source_id)
        session.run(
            "MATCH (a {id: $source_id}) SET a.status = 'merged', a.merged_into = $target_id",
            source_id=source_id,
            target_id=target_id,
        )


async def merge_nodes(source_node_id: str, target_node_id: str, reason: str, actor: str) -> dict:
    await anyio.to_thread.run_sync(_merge_nodes_in_neo4j, source_node_id, target_node_id)

    async with connection() as conn:
        await _log_change(
            conn,
            action="merge",
            target_type="node",
            target_id=source_node_id,
            actor=actor,
            reason=reason,
            after_state={"merged_into": target_node_id},
        )
    return {"source_node_id": source_node_id, "target_node_id": target_node_id, "status": "merged"}


def _deprecate_node_in_neo4j(node_id: str) -> str | None:
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            "MATCH (n {id: $id}) SET n.status = 'deprecated' RETURN n.id AS id", id=node_id
        ).single()
    return result["id"] if result is not None else None


def _deprecate_edge_in_neo4j(edge_id: str) -> str | None:
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            "MATCH ()-[r {id: $id}]->() SET r.status = 'deprecated' RETURN r.id AS id LIMIT 1",
            id=edge_id,
        ).single()
    return result["id"] if result is not None else None


async def delete_node(node_id: str, reason: str, actor: str) -> dict:
    if await anyio.to_thread.run_sync(_deprecate_node_in_neo4j, node_id) is None:
        raise CurationError(404, f"node {node_id} not found")

    async with connection() as conn:
        await _log_change(
            conn, action="delete", target_type="node", target_id=node_id, actor=actor, reason=reason
        )
    return {"node_id": node_id, "status": "deprecated"}


async def delete_edge(edge_id: str, reason: str, actor: str) -> dict:
    if await anyio.to_thread.run_sync(_deprecate_edge_in_neo4j, edge_id) is None:
        raise CurationError(404, f"edge {edge_id} not found")

    async with connection() as conn:
        await _log_change(
            conn, action="delete", target_type="edge", target_id=edge_id, actor=actor, reason=reason
        )
    return {"edge_id": edge_id, "status": "deprecated"}
