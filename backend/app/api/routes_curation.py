from fastapi import APIRouter, HTTPException, Query

from app.curation import service
from app.schemas.curation import (
    ApproveRejectRequest,
    CurationItemCreate,
    CurationItemResponse,
    DeleteEdgeRequest,
    DeleteNodeRequest,
    MergeNodesRequest,
)

router = APIRouter(prefix="/admin")


@router.get("/curation/items", response_model=list[CurationItemResponse])
async def list_curation_items(
    status: str | None = Query(default=None),
    item_type: str | None = Query(default=None),
) -> list[CurationItemResponse]:
    rows = await service.list_items(status, item_type)
    return [CurationItemResponse(**row) for row in rows]


@router.post("/curation/items", status_code=201)
async def create_curation_item(body: CurationItemCreate) -> dict:
    item_id = await service.create_item(body.item_type, body.action, body.payload, body.reason)
    return {"item_id": item_id, "status": "proposed"}


@router.post("/curation/items/{item_id}/approve")
async def approve_curation_item(item_id: str, body: ApproveRejectRequest) -> dict:
    try:
        return await service.approve_item(item_id, body.reviewer, body.reason)
    except service.CurationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/curation/items/{item_id}/reject")
async def reject_curation_item(item_id: str, body: ApproveRejectRequest) -> dict:
    try:
        return await service.reject_item(item_id, body.reviewer, body.reason)
    except service.CurationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/graph/merge-nodes")
async def merge_nodes_endpoint(body: MergeNodesRequest) -> dict:
    return await service.merge_nodes(body.source_node_id, body.target_node_id, body.reason, actor="human")


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
