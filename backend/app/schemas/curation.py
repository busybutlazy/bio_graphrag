from datetime import datetime

from pydantic import BaseModel, Field

# Review-payload limits (see docs/api_contract.md section 1). Both values land verbatim in
# `graph_change_logs`, and the gap flow actively invites a long free-text explanation, so the
# audit log needs a bound like every other request field (review finding L5).
MAX_REVIEWER_LEN = 100
MAX_REASON_LEN = 2000


# `CurationItemCreate` was removed with the single-item write path — proposing one loose element
# skipped both gates. The unit of proposal is a statement: see `CurationGroupCreate`.


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
    reviewer: str = Field(max_length=MAX_REVIEWER_LEN)
    reason: str | None = Field(default=None, max_length=MAX_REASON_LEN)


class SchemaGapRequest(BaseModel):
    """Record a proposal group as a schema gap. ``schema_gap_type`` is validated against the
    taxonomy whitelist in the service (422 on an unknown code), so the schema stays structural."""

    reviewer: str = Field(max_length=MAX_REVIEWER_LEN)
    reason: str | None = Field(default=None, max_length=MAX_REASON_LEN)
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
