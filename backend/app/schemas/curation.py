from datetime import datetime

from pydantic import BaseModel


class CurationItemCreate(BaseModel):
    item_type: str
    action: str
    payload: dict
    reason: str | None = None


class CurationItemResponse(BaseModel):
    item_id: str
    item_type: str
    action: str
    payload: dict
    status: str
    proposed_by: str
    reviewed_by: str | None = None
    reason: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class ApproveRejectRequest(BaseModel):
    reviewer: str
    reason: str | None = None


class MergeNodesRequest(BaseModel):
    source_node_id: str
    target_node_id: str
    reason: str


class DeleteNodeRequest(BaseModel):
    node_id: str
    reason: str


class DeleteEdgeRequest(BaseModel):
    edge_id: str
    reason: str
