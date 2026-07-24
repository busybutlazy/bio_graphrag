"""Group-level review endpoints — the unified two-gate governance surface.

A *proposal group* (curation_items sharing a group_id = one biological statement) is
listed with its Schema gate (engineer_gate) + Expert lens (back_translation) computed
live, then approved/rejected as one unit. Approve writes all member nodes/edges to the
approved graph + an audit row; reject writes nothing. Admin-gated like other /admin/*.
See changes/unified-two-gate-review/.
"""

from fastapi import APIRouter, Depends

from app.api.auth import require_admin
from app.api.errors import APIError
from app.curation import service
from app.schemas.curation import ApproveRejectRequest

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])

# CurationError -> the documented error contract {"error": {code, message}}.
# (The older /admin/curation routes raise HTTPException and emit {"detail": ...}; new
# surface follows CLAUDE.md instead of extending that deviation.)
_ERROR_CODES = {404: "not_found", 409: "conflict", 422: "invalid_request"}


def _as_api_error(exc: service.CurationError) -> APIError:
    return APIError(exc.status_code, _ERROR_CODES.get(exc.status_code, "error"), exc.message)


@router.get("/review/groups")
async def list_review_groups() -> list[dict]:
    return await service.list_groups()


@router.post("/review/groups/{group_id}/approve")
async def approve_review_group(group_id: str, body: ApproveRejectRequest) -> dict:
    try:
        return await service.approve_group(group_id, body.reviewer, body.reason)
    except service.CurationError as exc:
        raise _as_api_error(exc) from exc


@router.post("/review/groups/{group_id}/reject")
async def reject_review_group(group_id: str, body: ApproveRejectRequest) -> dict:
    try:
        return await service.reject_group(group_id, body.reviewer, body.reason)
    except service.CurationError as exc:
        raise _as_api_error(exc) from exc
