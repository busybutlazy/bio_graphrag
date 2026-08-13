"""Curation endpoints.

**There is no single-item write path here, and that is deliberate.** This module used to
expose `POST /curation/items` (propose one element) and `POST /curation/items/{id}/approve`
(write it straight into Neo4j). Together they formed a complete parallel route that bypassed
both gates: `create_item` wrote rows without a `group_id`, so `list_groups` never showed them,
and `approve_item` checked only `status == 'proposed'` before writing — no Schema gate, no
back-translation for the expert, no deprecated-resurrection check, no dangling-edge check.
`approve_group` has all four.

Knowledge now reaches the graph through exactly one door: propose a *statement* via
`POST /curation/groups`, dispose of it via `POST /admin/review/groups/{id}/{approve,reject,gap}`.
Anyone re-adding a per-item approval has to bring the gates with it.

`GET /curation/items` stays: it writes nothing, and it is the only way to see legacy rows that
predate grouping.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import require_admin
from app.api.errors import APIError
from app.curation import service
from app.schemas.curation import (
    CurationGroupCreate,
    CurationItemResponse,
    DeleteEdgeRequest,
    DeleteNodeRequest,
    MergeNodesRequest,
)

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])

# The grouped-propose endpoint follows the documented {"error":{code,message}} contract (like
# /admin/review/*), not the {"detail"} shape the older single-item routes below still emit.
_ERROR_CODES = {404: "not_found", 409: "conflict", 422: "invalid_request"}


def _as_api_error(exc: service.CurationError) -> APIError:
    return APIError(exc.status_code, _ERROR_CODES.get(exc.status_code, "error"), exc.message)


@router.get("/curation/items", response_model=list[CurationItemResponse])
async def list_curation_items(
    status: str | None = Query(default=None),
    item_type: str | None = Query(default=None),
) -> list[CurationItemResponse]:
    rows = await service.list_items(status, item_type)
    return [CurationItemResponse(**row) for row in rows]


@router.post("/curation/groups", status_code=201)
async def create_curation_group(body: CurationGroupCreate) -> dict:
    """Stage a hand-made proposal group (nodes+edges statement) → the group Review queue."""
    try:
        return await service.create_group(
            body.proposed_nodes,
            body.proposed_edges,
            body.reason,
            body.possible_schema_gap,
        )
    except service.CurationError as exc:
        raise _as_api_error(exc) from exc


@router.post("/graph/merge-nodes")
async def merge_nodes_endpoint(body: MergeNodesRequest) -> dict:
    try:
        return await service.merge_nodes(
            body.source_node_id, body.target_node_id, body.reason, actor="human"
        )
    except service.CurationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/graph/delete-node")
async def delete_node_endpoint(body: DeleteNodeRequest) -> dict:
    try:
        return await service.delete_node(body.node_id, body.reason, actor="human")
    except service.CurationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/graph/delete-edge")
async def delete_edge_endpoint(body: DeleteEdgeRequest) -> dict:
    try:
        return await service.delete_edge(body.edge_id, body.reason, actor="human")
    except service.CurationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
