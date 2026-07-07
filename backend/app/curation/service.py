import json
import uuid

import asyncpg

from app.core.config import settings
from app.db.neo4j_driver import get_driver
from ingestion.pipeline import load_neo4j


class CurationError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )


def _load_payload(row: asyncpg.Record) -> dict:
    payload = row["payload"]
    return json.loads(payload) if isinstance(payload, str) else payload


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
) -> None:
    change_id = f"change:{uuid.uuid4()}"
    await conn.execute(
        """
        INSERT INTO graph_change_logs
            (change_id, curation_item_id, action, target_type, target_id, actor, reason, before_state, after_state)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        change_id, curation_item_id, action, target_type, target_id, actor, reason,
        json.dumps(before_state) if before_state is not None else None,
        json.dumps(after_state) if after_state is not None else None,
    )


async def list_items(status: str | None, item_type: str | None) -> list[dict]:
    conn = await _connect()
    try:
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
        return [{**dict(row), "payload": _load_payload(row)} for row in rows]
    finally:
        await conn.close()


async def create_item(item_type: str, action: str, payload: dict, reason: str | None) -> str:
    payload = {**payload, "status": "proposed"}
    item_id = f"curation:{payload['id']}"
    conn = await _connect()
    try:
        await conn.execute(
            """
            INSERT INTO curation_items (item_id, item_type, action, payload, status, proposed_by, reason)
            VALUES ($1, $2, $3, $4, 'proposed', 'human', $5)
            """,
            item_id, item_type, action, json.dumps(payload), reason,
        )
    finally:
        await conn.close()
    return item_id


async def approve_item(item_id: str, reviewer: str, reason: str | None) -> dict:
    conn = await _connect()
    try:
        row = await conn.fetchrow("SELECT * FROM curation_items WHERE item_id = $1", item_id)
        if row is None:
            raise CurationError(404, f"curation item {item_id} not found")
        if row["status"] != "proposed":
            raise CurationError(409, f"curation item {item_id} is not in proposed state")

        payload = _load_payload(row)
        payload["status"] = "approved"

        driver = get_driver()
        if row["item_type"] == "node":
            load_neo4j.write_nodes(driver, [payload])
        else:
            load_neo4j.write_edges(driver, [payload])

        await conn.execute(
            """
            UPDATE curation_items SET status = 'approved', reviewed_by = $2, reason = $3, reviewed_at = now()
            WHERE item_id = $1
            """,
            item_id, reviewer, reason,
        )
        await _log_change(
            conn, action="approve", target_type=row["item_type"], target_id=payload["id"],
            actor=reviewer, reason=reason, curation_item_id=row["id"], after_state=payload,
        )
        return {"item_id": item_id, "status": "approved"}
    finally:
        await conn.close()


async def reject_item(item_id: str, reviewer: str, reason: str | None) -> dict:
    conn = await _connect()
    try:
        row = await conn.fetchrow("SELECT * FROM curation_items WHERE item_id = $1", item_id)
        if row is None:
            raise CurationError(404, f"curation item {item_id} not found")
        if row["status"] != "proposed":
            raise CurationError(409, f"curation item {item_id} is not in proposed state")

        payload = _load_payload(row)
        await conn.execute(
            """
            UPDATE curation_items SET status = 'rejected', reviewed_by = $2, reason = $3, reviewed_at = now()
            WHERE item_id = $1
            """,
            item_id, reviewer, reason,
        )
        await _log_change(
            conn, action="reject", target_type=row["item_type"], target_id=payload["id"],
            actor=reviewer, reason=reason, curation_item_id=row["id"],
        )
        return {"item_id": item_id, "status": "rejected"}
    finally:
        await conn.close()


def _merge_nodes_in_neo4j(source_id: str, target_id: str) -> None:
    driver = get_driver()
    with driver.session() as session:
        outgoing = session.run(
            "MATCH (a {id: $source_id})-[r]->(b) WHERE b.id <> $target_id "
            "RETURN type(r) AS type, properties(r) AS props, b.id AS other_id, r.id AS rel_id",
            source_id=source_id, target_id=target_id,
        ).data()
        incoming = session.run(
            "MATCH (b)-[r]->(a {id: $source_id}) WHERE b.id <> $target_id "
            "RETURN type(r) AS type, properties(r) AS props, b.id AS other_id, r.id AS rel_id",
            source_id=source_id, target_id=target_id,
        ).data()

        for rel in outgoing:
            session.run(
                f"MATCH (t {{id: $target_id}}), (o {{id: $other_id}}) "
                f"MERGE (t)-[r2:{rel['type']} {{id: $rel_id}}]->(o) SET r2 += $props",
                target_id=target_id, other_id=rel["other_id"], rel_id=rel["rel_id"], props=rel["props"],
            )
        for rel in incoming:
            session.run(
                f"MATCH (t {{id: $target_id}}), (o {{id: $other_id}}) "
                f"MERGE (o)-[r2:{rel['type']} {{id: $rel_id}}]->(t) SET r2 += $props",
                target_id=target_id, other_id=rel["other_id"], rel_id=rel["rel_id"], props=rel["props"],
            )

        session.run("MATCH (a {id: $source_id})-[r]-() DELETE r", source_id=source_id)
        session.run(
            "MATCH (a {id: $source_id}) SET a.status = 'merged', a.merged_into = $target_id",
            source_id=source_id, target_id=target_id,
        )


async def merge_nodes(source_node_id: str, target_node_id: str, reason: str, actor: str) -> dict:
    _merge_nodes_in_neo4j(source_node_id, target_node_id)

    conn = await _connect()
    try:
        await _log_change(
            conn, action="merge", target_type="node", target_id=source_node_id,
            actor=actor, reason=reason, after_state={"merged_into": target_node_id},
        )
    finally:
        await conn.close()
    return {"source_node_id": source_node_id, "target_node_id": target_node_id, "status": "merged"}


async def delete_node(node_id: str, reason: str, actor: str) -> dict:
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            "MATCH (n {id: $id}) SET n.status = 'deprecated' RETURN n.id AS id", id=node_id
        ).single()
    if result is None:
        raise CurationError(404, f"node {node_id} not found")

    conn = await _connect()
    try:
        await _log_change(conn, action="delete", target_type="node", target_id=node_id, actor=actor, reason=reason)
    finally:
        await conn.close()
    return {"node_id": node_id, "status": "deprecated"}


async def delete_edge(edge_id: str, reason: str, actor: str) -> dict:
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            "MATCH ()-[r {id: $id}]->() SET r.status = 'deprecated' RETURN r.id AS id LIMIT 1", id=edge_id
        ).single()
    if result is None:
        raise CurationError(404, f"edge {edge_id} not found")

    conn = await _connect()
    try:
        await _log_change(conn, action="delete", target_type="edge", target_id=edge_id, actor=actor, reason=reason)
    finally:
        await conn.close()
    return {"edge_id": edge_id, "status": "deprecated"}
