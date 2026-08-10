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


class CurationGroupCreate(BaseModel):
    """A hand-made proposal group — a nodes+edges statement staged as one review unit.

    Structural only; business rules (non-empty, element cap, duplicate ids, type whitelist) are
    enforced in ``service.create_group`` so every rejection follows the ``{"error":{…}}`` contract
    rather than FastAPI's default validation shape.
    """

    proposed_nodes: list[dict] = []
    proposed_edges: list[dict] = []
    reason: str | None = None
    possible_schema_gap: bool = False


class ApproveRejectRequest(BaseModel):
    reviewer: str
    reason: str | None = None


class SchemaGapRequest(BaseModel):
    """Record a proposal group as a schema gap. ``schema_gap_type`` is validated against the
    taxonomy whitelist in the service (422 on an unknown code), so the schema stays structural."""

    reviewer: str
    reason: str | None = None
    schema_gap_type: str


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
