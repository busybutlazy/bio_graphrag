import json
import uuid
from collections import Counter

import anyio
import asyncpg

from app.db.neo4j_driver import get_driver
from app.db.pool import connection
from app.graph.back_translation import build_context, render_understanding
from app.graph.engineer_gate import evaluate as evaluate_schema_gate
from ingestion.pipeline import load_neo4j
from ingestion.pipeline.normalize_concepts import (
    VALID_NODE_TYPES,
    VALID_RELATIONSHIP_TYPES,
)

# Upper bound on how many nodes+edges one hand-made proposal group may carry. A statement is a
# small unit; the cap keeps a single request bounded (mirrors the project's request-limit posture).
MAX_GROUP_ELEMENTS = 20

# Plain-language ⇄ code schema-gap taxonomy (docs/schema-gap-policy.md). The reviewer picks a plain
# option in the UI; the endpoint validates the resulting code against this whitelist so free text can
# never enter the audit semantics.
VALID_SCHEMA_GAP_TYPES = frozenset(
    {
        "permissive_effect",
        "antagonistic_or_synergistic_interaction",
        "pathway_or_cascade",
        "conditional_effect",
        "threshold_effect",
        "unknown",
    }
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


# `create_item` / `approve_item` / `reject_item` used to live here. They were removed, not
# misplaced: `create_item` staged rows with no `group_id` (invisible to `list_groups`, and so to
# the reviewer), and `approve_item` wrote a payload into Neo4j behind nothing but a
# `status == 'proposed'` check. Between them, knowledge could reach the student-facing graph
# without passing either gate. Proposing is now `create_group`; disposing is `approve_group` /
# `reject_group` / `record_gap`, and every one of them goes through the guards documented on
# `approve_group`.


async def create_group(
    proposed_nodes: list[dict],
    proposed_edges: list[dict],
    reason: str | None = None,
    possible_schema_gap: bool = False,
    proposed_by: str = "human",
) -> dict:
    """Stage a hand-made proposal group — a nodes+edges *statement* — as ``proposed``
    curation_items sharing one ``group_id``, so it flows straight into the group Review queue and
    its two gates (Schema gate + expert lens are computed live by ``list_groups``).

    Every element is validated against the type whitelists up front (the injection guard), so a
    bad type can never reach Cypher label interpolation on approval. All inserts run inside a
    single transaction: a failure on any element rolls the whole group back — nothing is staged.

    ``possible_schema_gap`` and the proposer's ``reason`` are stashed in each member's
    ``schema_check`` (``group_possible_schema_gap`` / ``propose_reason``) so ``list_groups`` can
    surface them without a new column, and so the reason survives an approve/reject overwriting
    ``curation_items.reason`` with the *reviewer's* reason. The stored ``schema_check`` is otherwise
    unused — the live gate does the real evaluation.
    """
    total = len(proposed_nodes) + len(proposed_edges)
    if total == 0:
        raise CurationError(422, "a proposal group needs at least one node or edge")
    if total > MAX_GROUP_ELEMENTS:
        raise CurationError(
            422,
            f"a proposal group may contain at most {MAX_GROUP_ELEMENTS} elements; got {total}",
        )

    for node in proposed_nodes:
        _validate_curation_payload("node", node)
    for edge in proposed_edges:
        _validate_curation_payload("edge", edge)

    # Intra-group duplicate-id guard: item_id is ``curation:{group_id}:{elem_id}``, so a repeated
    # id would PK-collide mid-transaction. Reject up front across the combined node+edge id set.
    ids = [n["id"] for n in proposed_nodes] + [e["id"] for e in proposed_edges]
    dupes = sorted(i for i, c in Counter(ids).items() if c > 1)
    if dupes:
        raise CurationError(422, f"duplicate element id(s) within the group: {', '.join(dupes)}")

    # Dangling-endpoint guard (review F2): every edge endpoint must resolve to a node proposed in
    # this same group OR one already in the approved graph. Otherwise the Schema gate passes, but
    # ``load_neo4j.write_edges``'s MATCH finds nothing at approval, the MERGE silently no-ops, and
    # the audit log records an edge that was never written. Reject at propose time instead.
    # A missing/empty endpoint is the same hole (`""` is falsy and would slip a bare filter, then
    # `MATCH (a {id:""})` no-ops the same way), so reject those explicitly first (review R4).
    for e in proposed_edges:
        if not e.get("source") or not e.get("target"):
            raise CurationError(422, f"edge {e.get('id')!r} needs a non-empty source and target")
    proposed_ids = {n["id"] for n in proposed_nodes}
    referenced = {ep for e in proposed_edges for ep in (e["source"], e["target"])}
    external = referenced - proposed_ids
    if external:
        # Existence check (not a label lookup — a real but unlabelled approved node must still
        # resolve; review R2), so the guard never false-rejects an edge into the approved graph.
        found = await anyio.to_thread.run_sync(
            _existing_approved_ids, get_driver(), sorted(external), []
        )
        unresolved = sorted(external - set(found["nodes"]))
        if unresolved:
            raise CurationError(
                422,
                "edge endpoint(s) not found as a proposed node in this group or an approved "
                f"node: {', '.join(unresolved)}",
            )

    # Hand-made knowledge has no source chunk, but extraction_output_schema requires
    # ``source_chunk_id`` on every node/edge (the schema gate validates against it). Stamp a
    # namespaced provenance marker so a hand-authored statement can pass the gate; the author *is*
    # the source. Namespaced (``manual:{proposed_by}``) per the project's ``prefix:id`` convention
    # so it can never collide with a real chunk id (review F8).
    provenance = f"manual:{proposed_by}"

    def _with_provenance(elem: dict) -> dict:
        return elem if elem.get("source_chunk_id") else {**elem, "source_chunk_id": provenance}

    member_check: dict = {}
    if possible_schema_gap:
        member_check["group_possible_schema_gap"] = True
    if reason:
        member_check["propose_reason"] = reason

    group_id = f"group:{proposed_by}:{uuid.uuid4()}"
    check_json = json.dumps(member_check)
    elements = [("node", _with_provenance(n)) for n in proposed_nodes] + [
        ("edge", _with_provenance(e)) for e in proposed_edges
    ]

    async with connection() as conn:
        async with conn.transaction():
            for item_type, elem in elements:
                await conn.execute(
                    """
                    INSERT INTO curation_items
                        (item_id, item_type, action, payload, status, proposed_by, schema_check, group_id)
                    VALUES ($1, $2, 'create', $3, 'proposed', $4, $5, $6)
                    """,
                    f"curation:{group_id}:{elem['id']}",
                    item_type,
                    json.dumps({**elem, "status": "proposed"}),
                    proposed_by,
                    check_json,
                    group_id,
                )
    return {"group_id": group_id, "nodes": len(proposed_nodes), "edges": len(proposed_edges)}


# --- Group-level review (unified two-gate: schema gate + expert gate) -----------------
# A "proposal group" is the set of curation_items sharing a group_id — the nodes+edges of
# one biological statement, reviewed as one unit. Its shape matches what engineer_gate and
# back_translation already expect. See changes/unified-two-gate-review/.


def _proposal_from_items(items: list) -> dict:
    """Assemble grouped curation_items into an extraction-shaped proposal.

    Strips the curation-internal ``status`` key so payloads validate against
    ``extraction_output_schema`` (additionalProperties: false).
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    for it in items:
        payload = {k: v for k, v in _load_json(it["payload"]).items() if k != "status"}
        (nodes if it["item_type"] == "node" else edges).append(payload)
    return {"proposed_nodes": nodes, "proposed_edges": edges}


def _group_possible_schema_gap(items: list) -> bool:
    """D5: a group is a genuine schema gap only if explicitly flagged (stashed in ``schema_check``
    by the seeder / proposer). The flag is what makes the renderer produce a gap sentence and the
    gate answer ``needs_schema_extension``, so every path that evaluates a group's gate must apply
    it — otherwise the queue and the dispose endpoints would disagree about the same group.
    """
    return any(
        (_load_json(it["schema_check"]) or {}).get("group_possible_schema_gap") for it in items
    )


def _deprecated_member_ids(driver, node_ids: list[str], edge_ids: list[str]) -> dict:
    """Which of these ids exist but were **deleted** by a curator? (sync — run in a thread)

    Deletion here is a status change, not a removal: ``delete_node`` sets ``status='deprecated'`` and
    leaves the element in the graph. So a re-proposal of a deleted concept would sail past an
    approved-only lookup, and ``write_nodes``' ``MERGE … SET n.status`` would flip it back to
    approved — undoing a human decision as a side effect of approving something else. Restoring
    deleted knowledge has to be a decision someone makes on purpose.
    """
    found: dict[str, list[str]] = {"nodes": [], "edges": []}
    with driver.session() as session:
        if node_ids:
            found["nodes"] = [
                r["id"]
                for r in session.run(
                    "MATCH (n) WHERE n.id IN $ids AND n.status = 'deprecated' RETURN n.id AS id",
                    ids=node_ids,
                )
            ]
        if edge_ids:
            found["edges"] = [
                r["id"]
                for r in session.run(
                    "MATCH ()-[r]->() WHERE r.id IN $ids AND r.status = 'deprecated' "
                    "RETURN r.id AS id",
                    ids=edge_ids,
                )
            ]
    return found


def _existing_approved_ids(driver, node_ids: list[str], edge_ids: list[str]) -> dict:
    """Which of these ids already exist in the **approved** graph? (sync — run in a thread)"""
    found: dict[str, list[str]] = {"nodes": [], "edges": []}
    with driver.session() as session:
        if node_ids:
            found["nodes"] = [
                r["id"]
                for r in session.run(
                    "MATCH (n) WHERE n.id IN $ids AND n.status = 'approved' RETURN n.id AS id",
                    ids=node_ids,
                )
            ]
        if edge_ids:
            found["edges"] = [
                r["id"]
                for r in session.run(
                    "MATCH ()-[r]->() WHERE r.id IN $ids AND r.status = 'approved' RETURN r.id AS id",
                    ids=edge_ids,
                )
            ]
    return found


def _approved_labels(driver, node_ids: list[str]) -> dict:
    """Labels of approved nodes, so the expert lens names referenced concepts properly."""
    if not node_ids:
        return {}
    with driver.session() as session:
        return {
            r["id"]: r["label"]
            for r in session.run(
                "MATCH (n) WHERE n.id IN $ids AND n.status = 'approved' "
                "RETURN n.id AS id, n.label AS label",
                ids=node_ids,
            )
            if r["label"]
        }


async def list_groups() -> list[dict]:
    """List proposed proposal-groups with a live schema gate + expert-lens understanding."""
    async with connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM curation_items "
            "WHERE group_id IS NOT NULL AND status = 'proposed' "
            "ORDER BY group_id, created_at"
        )
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row["group_id"], []).append(row)

    proposals = {gid: _proposal_from_items(items) for gid, items in grouped.items()}
    # Surface the gap flag on the proposal so the renderer + gate can branch.
    for gid, items in grouped.items():
        if _group_possible_schema_gap(items):
            proposals[gid]["possible_schema_gap"] = True
    # cross-group ctx so references_existing labels resolve in the expert lens
    ctx = build_context([{"proposal": p} for p in proposals.values()])

    # An edge may attach to a node that already lives in the approved graph (referenced,
    # not proposed). Resolve those labels too, else the lens shows a humanized id.
    proposed_ids = {n["id"] for p in proposals.values() for n in p["proposed_nodes"]}
    referenced = {
        endpoint
        for p in proposals.values()
        for e in p["proposed_edges"]
        for endpoint in (e.get("source"), e.get("target"))
        if endpoint and endpoint not in proposed_ids
    }
    if referenced:
        extra = await anyio.to_thread.run_sync(_approved_labels, get_driver(), sorted(referenced))
        for nid, label in extra.items():
            ctx["labels"].setdefault(nid, label)

    def _propose_reason(items: list) -> str | None:
        for it in items:
            reason = (_load_json(it["schema_check"]) or {}).get("propose_reason")
            if reason:
                return reason
        return None

    return [
        {
            "group_id": gid,
            "proposed_by": items[0]["proposed_by"],
            "item_ids": [it["item_id"] for it in items],
            "proposal": proposals[gid],
            "propose_reason": _propose_reason(items),
            "schema_gate": evaluate_schema_gate(proposals[gid]),
            "understanding": render_understanding(proposals[gid], ctx),
        }
        for gid, items in grouped.items()
    ]


async def approve_group(group_id: str, reviewer: str, reason: str | None) -> dict:
    """Approve every proposed item in a group.

    Guards, in order — a group only reaches the graph if all pass:

    1. group exists (404) and still has proposed items (409);
    2. every member is an ``action='create'`` (the only verb this path implements);
    3. the **Schema gate is enforcing** — ``result != 'pass'`` is refused (409). An audited
       engineer override may be added later; today a failing form never reaches the graph;
    4. every edge has a non-empty source and target (422);
    5. every edge endpoint is either proposed in this group or already approved (409) — a group may
       legitimately reference a node another statement proposes, but only once that node exists,
       or the edge would be written into nothing.

    Members that already exist in the approved graph are **reused, not rewritten** — see the note at
    the write site. A node many statements talk about belongs to all of them; refusing the group for
    that reason once meant only one statement per paragraph could ever be approved.

    Row selection is ``FOR UPDATE`` inside the transaction so two concurrent approvals
    cannot both observe ``proposed``. Neo4j writes happen inside the same block, so a
    failure aborts the Postgres commit; the writes themselves are idempotent MERGEs.
    """
    async with connection() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                "SELECT * FROM curation_items WHERE group_id = $1 FOR UPDATE", group_id
            )
            if not rows:
                raise CurationError(404, f"review group {group_id} not found")
            proposed = [r for r in rows if r["status"] == "proposed"]
            if not proposed:
                raise CurationError(409, f"review group {group_id} has no proposed items")

            bad_actions = sorted({r["action"] for r in proposed if r["action"] != "create"})
            if bad_actions:
                raise CurationError(
                    422,
                    f"group approval supports action 'create' only; got {bad_actions}",
                )

            proposal = _proposal_from_items(proposed)
            if _group_possible_schema_gap(proposed):
                proposal["possible_schema_gap"] = True
            gate = evaluate_schema_gate(proposal)
            if gate["result"] != "pass":
                raise CurationError(
                    409,
                    f"schema gate did not pass ({gate['result']}); "
                    f"group {group_id} cannot be approved",
                )

            node_payloads: list[dict] = []
            edge_payloads: list[dict] = []
            for r in proposed:
                payload = _load_json(r["payload"])
                payload["status"] = "approved"
                (node_payloads if r["item_type"] == "node" else edge_payloads).append(payload)

            driver = get_driver()
            existing = await anyio.to_thread.run_sync(
                _existing_approved_ids,
                driver,
                [n["id"] for n in node_payloads],
                [e["id"] for e in edge_payloads],
            )
            # A member that already exists approved is **reused, not rewritten**. In a graph one
            # node carries many relationships, so a concept every statement in a paragraph talks
            # about — insulin, blood glucose — necessarily appears in several proposal groups. The
            # graph layer has always handled that (`MERGE` on id); what did not was this guard,
            # which refused the whole group and so let a reviewer approve only one statement per
            # paragraph no matter which they picked.
            #
            # The risk it was written for is real but narrower: `write_nodes` follows its MERGE with
            # an unconditional `SET n.label/.description`, so re-approving would silently replace
            # curated wording with the proposal's. Skipping the write removes that risk outright —
            # the curated version always wins — and the reused ids go into the audit row so the
            # decision is visible rather than implied.
            reused_nodes = set(existing["nodes"])
            reused_edges = set(existing["edges"])
            node_writes = [n for n in node_payloads if n["id"] not in reused_nodes]
            edge_writes = [e for e in edge_payloads if e["id"] not in reused_edges]

            # "Reuse, don't rewrite" only protects what is *approved*. A member a curator deleted
            # sits in the graph as `deprecated`, so an approved-only lookup misses it and the write
            # below would MERGE it back to approved with the proposal's wording — quietly reversing
            # a deletion as a side effect of approving something else. Restoring deleted knowledge
            # is a decision, so it is refused here rather than performed silently.
            buried = await anyio.to_thread.run_sync(
                _deprecated_member_ids,
                driver,
                [n["id"] for n in node_writes],
                [e["id"] for e in edge_writes],
            )
            resurrected = sorted(buried["nodes"] + buried["edges"])
            if resurrected:
                raise CurationError(
                    409,
                    f"group {group_id} re-proposes knowledge a curator deleted "
                    f"({', '.join(resurrected)}); approving would restore it — "
                    "decide that explicitly instead",
                )

            # A group may legitimately reference a node it does not propose — an interaction is a
            # claim *about* effects that are their own statements, so it points at them rather than
            # re-proposing them. That reference is only sound once the referenced node exists:
            # approving out of order would write an edge into nothing. `create_group` makes the same
            # check at propose time, but a group can be staged (extraction path) or approved in an
            # order that leaves it unsatisfied, so the graph-writing path has to enforce it too.
            referenced: set[str] = set()
            for edge in edge_payloads:
                source, target = edge.get("source"), edge.get("target")
                if not source or not target:
                    # `""` is falsy and would slip a bare filter, then `MATCH (a {id:""})` no-ops —
                    # the same hole create_group closes at propose time (review R4).
                    raise CurationError(
                        422, f"edge {edge.get('id')!r} needs a non-empty source and target"
                    )
                referenced.update((source, target))

            external = sorted(referenced - {n["id"] for n in node_payloads})
            if external:
                found = await anyio.to_thread.run_sync(_existing_approved_ids, driver, external, [])
                missing = sorted(set(external) - set(found["nodes"]))
                if missing:
                    raise CurationError(
                        409,
                        f"group {group_id} has edge endpoint(s) that are neither proposed in this "
                        f"group nor already approved: {', '.join(missing)}; "
                        "approve the group that proposes them first",
                    )

            if node_writes:
                await anyio.to_thread.run_sync(load_neo4j.write_nodes, driver, node_writes)
            if edge_writes:
                await anyio.to_thread.run_sync(load_neo4j.write_edges, driver, edge_writes)
            await conn.execute(
                "UPDATE curation_items SET status = 'approved', reviewed_by = $2, "
                "reason = $3, reviewed_at = now() WHERE group_id = $1 AND status = 'proposed'",
                group_id,
                reviewer,
                reason,
            )
            await _log_change(
                conn,
                action="approve",
                target_type="proposal_group",
                target_id=group_id,
                actor=reviewer,
                reason=reason,
                # Audit the full delta, not just ids: the log must be able to reconstruct
                # exactly what entered the graph.
                before_state={
                    "members_existed_in_graph": sorted(reused_nodes | reused_edges),
                    "schema_gate": gate["result"],
                },
                after_state={
                    "item_ids": [r["item_id"] for r in proposed],
                    "nodes": node_writes,
                    "edges": edge_writes,
                    # what this approval deliberately did NOT write, so "the curated version won"
                    # is a recorded decision rather than an absence in the log
                    "reused_nodes": sorted(reused_nodes),
                    "reused_edges": sorted(reused_edges),
                },
            )
        return {
            "group_id": group_id,
            "status": "approved",
            "nodes": len(node_writes),
            "edges": len(edge_writes),
            "reused_nodes": len(reused_nodes),
            "reused_edges": len(reused_edges),
        }


async def reject_group(group_id: str, reviewer: str, reason: str | None) -> dict:
    """Reject every proposed item in a group; writes nothing to Neo4j, appends one audit row.

    Rejection is always allowed regardless of the Schema gate — a failing proposal is
    exactly the thing a reviewer should be able to turn away.
    """
    async with connection() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                "SELECT * FROM curation_items WHERE group_id = $1 FOR UPDATE", group_id
            )
            if not rows:
                raise CurationError(404, f"review group {group_id} not found")
            proposed = [r for r in rows if r["status"] == "proposed"]
            if not proposed:
                raise CurationError(409, f"review group {group_id} has no proposed items")
            await conn.execute(
                "UPDATE curation_items SET status = 'rejected', reviewed_by = $2, "
                "reason = $3, reviewed_at = now() WHERE group_id = $1 AND status = 'proposed'",
                group_id,
                reviewer,
                reason,
            )
            await _log_change(
                conn,
                action="reject",
                target_type="proposal_group",
                target_id=group_id,
                actor=reviewer,
                reason=reason,
                after_state={"item_ids": [r["item_id"] for r in proposed]},
            )
        return {"group_id": group_id, "status": "rejected"}


async def record_group_gap(
    group_id: str, reviewer: str, reason: str | None, schema_gap_type: str
) -> dict:
    """Record a proposal group as a **schema gap** — the expert judges the current schema cannot
    express its real meaning (distinct from a *form* problem, which is a reject).

    Enforcing, and only for a group the Schema gate flags ``needs_schema_extension``. Sets the
    group's ``proposed`` members to ``status='schema_gap'`` and appends exactly ONE
    ``graph_change_logs`` row; writes nothing to Neo4j. The status UPDATE and the audit INSERT share a
    single transaction — either both commit or both roll back.
    """
    if not reviewer or not reviewer.strip():
        raise CurationError(422, "reviewer is required")
    if schema_gap_type not in VALID_SCHEMA_GAP_TYPES:
        raise CurationError(422, f"invalid schema_gap_type: {schema_gap_type!r}")
    async with connection() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                "SELECT * FROM curation_items WHERE group_id = $1 FOR UPDATE", group_id
            )
            if not rows:
                raise CurationError(404, f"review group {group_id} not found")
            proposed = [r for r in rows if r["status"] == "proposed"]
            if not proposed:
                raise CurationError(409, f"review group {group_id} has no proposed items")
            proposal = _proposal_from_items(proposed)
            if _group_possible_schema_gap(proposed):
                proposal["possible_schema_gap"] = True
            gate = evaluate_schema_gate(proposal)
            if gate["result"] != "needs_schema_extension":
                raise CurationError(
                    409,
                    f"group {group_id} is not a schema gap (gate result {gate['result']!r}); "
                    "record-as-gap is only for needs_schema_extension",
                )
            await conn.execute(
                "UPDATE curation_items SET status = 'schema_gap', reviewed_by = $2, "
                "reason = $3, reviewed_at = now() WHERE group_id = $1 AND status = 'proposed'",
                group_id,
                reviewer,
                reason,
            )
            await _log_change(
                conn,
                action="schema_gap",
                target_type="proposal_group",
                target_id=group_id,
                actor=reviewer,
                reason=reason,
                after_state={
                    "schema_gap_type": schema_gap_type,
                    "item_ids": [r["item_id"] for r in proposed],
                },
            )
        return {"group_id": group_id, "status": "schema_gap", "schema_gap_type": schema_gap_type}


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
