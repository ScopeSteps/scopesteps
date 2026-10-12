from fastapi import APIRouter

from scopesteps.backlog.client import BacklogVersionId
from scopesteps.change_control.http.schemas import (
    ApproveRequest,
    ChangeSetResponse,
    DecisionResponse,
    RejectRequest,
)
from scopesteps.infrastructure.http import IdempotencyKey
from scopesteps.kernel.errors import FeatureNotImplementedError

router = APIRouter(tags=["change_control"])


@router.post("/backlogs/{version_id}/approve")
def approve_version(
    version_id: BacklogVersionId, body: ApproveRequest, idempotency_key: IdempotencyKey
) -> DecisionResponse:
    raise FeatureNotImplementedError("Approval")


@router.post("/backlogs/{version_id}/reject")
def reject_version(
    version_id: BacklogVersionId, body: RejectRequest, idempotency_key: IdempotencyKey
) -> DecisionResponse:
    raise FeatureNotImplementedError("Rejection")


@router.get("/backlogs/{version_id}/change-set")
def get_change_set(version_id: BacklogVersionId) -> ChangeSetResponse:
    raise FeatureNotImplementedError("Change sets")
