"""Group-level review endpoints — the unified two-gate governance surface.

A *proposal group* (curation_items sharing a group_id = one biological statement) is
listed with its Schema gate (engineer_gate) + Expert lens (back_translation) computed
live, then approved/rejected as one unit. Approve writes all member nodes/edges to the
approved graph + an audit row; reject writes nothing. Admin-gated like other /admin/*.
See changes/unified-two-gate-review/.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import require_admin
from app.curation import service
from app.schemas.curation import ApproveRejectRequest

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


@router.get("/review/groups")
async def list_review_groups() -> list[dict]:
    return await service.list_groups()


@router.post("/review/groups/{group_id}/approve")
async def approve_review_group(group_id: str, body: ApproveRejectRequest) -> dict:
    try:
        return await service.approve_group(group_id, body.reviewer, body.reason)
    except service.CurationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/review/groups/{group_id}/reject")
async def reject_review_group(group_id: str, body: ApproveRejectRequest) -> dict:
    try:
        return await service.reject_group(group_id, body.reviewer, body.reason)
    except service.CurationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
