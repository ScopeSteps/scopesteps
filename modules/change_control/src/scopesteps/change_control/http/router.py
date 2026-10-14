from collections.abc import Callable, Collection
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.client import BacklogVersionId, DecisionReader, VersionDecision
from scopesteps.change_control.application import decisions
from scopesteps.change_control.application.decisions import DecisionView
from scopesteps.change_control.domain.errors import DecisionInProgressError
from scopesteps.change_control.http.schemas import (
    ApproveRequest,
    ChangeSetResponse,
    DecisionResponse,
    RejectRequest,
)
from scopesteps.change_control.infrastructure.repository import BacklogVersions, SqlDecisionStore
from scopesteps.identity.client import ProjectAccessResolver, get_project_access_resolver
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import IdempotencyKey, SessionDep
from scopesteps.kernel.errors import FeatureNotImplementedError

router = APIRouter(tags=["change_control"])

ResolverDep = Annotated[ProjectAccessResolver, Depends(get_project_access_resolver)]


@router.post("/backlogs/{version_id}/approve")
def approve_version(
    version_id: BacklogVersionId,
    body: ApproveRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    session: SessionDep,
) -> DecisionResponse:
    """Approve the draft as the project's next baseline. Needs the approver role.

    Runs every approval check again; 409 `APPROVAL_BLOCKED` lists them in `details.checks`.
    409 `VERSION_CHANGED` or `BASELINE_CHANGED` means what was reviewed is stale: reload and
    review again rather than retrying.
    """
    view = _deciding(
        session,
        lambda: decisions.approve(
            BacklogVersions(session),
            SqlDecisionStore(session),
            audit_recorder(session),
            resolve,
            version_id,
            decisions.Approve(
                idempotency_key=idempotency_key,
                expected_revision=body.expected_revision,
                content_hash=body.content_hash,
                expected_baseline_id=body.expected_baseline_id,
            ),
            utc_now(),
        ),
    )
    return _response(view)


@router.post("/backlogs/{version_id}/reject")
def reject_version(
    version_id: BacklogVersionId,
    body: RejectRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    session: SessionDep,
) -> DecisionResponse:
    """Reject the draft; the baseline stays as it is. Needs the approver role."""
    view = _deciding(
        session,
        lambda: decisions.reject(
            BacklogVersions(session),
            SqlDecisionStore(session),
            audit_recorder(session),
            resolve,
            version_id,
            decisions.Reject(
                idempotency_key=idempotency_key,
                expected_revision=body.expected_revision,
                reason=body.reason,
            ),
            utc_now(),
        ),
    )
    return _response(view)


@router.get("/backlogs/{version_id}/change-set")
def get_change_set(version_id: BacklogVersionId) -> ChangeSetResponse:
    raise FeatureNotImplementedError("Change sets")


def resolve_decision_reader(session: SessionDep) -> DecisionReader:
    """The implementation the composition root binds to `backlog.client.get_decision_reader`."""
    store = SqlDecisionStore(session)

    def read(version_ids: Collection[BacklogVersionId]) -> dict[BacklogVersionId, VersionDecision]:
        return {
            version_id: VersionDecision(
                version_id=version_id,
                decision=decision.decision,
                decided_by=decision.decided_by,
                decided_at=decision.decided_at,
                baseline_number=decision.baseline_number,
            )
            for version_id, decision in store.of_versions(version_ids).items()
        }

    return read


def _deciding(session: Session, decide: Callable[[], DecisionView]) -> DecisionView:
    try:
        view = decide()
        session.commit()
    except IntegrityError as error:
        # A concurrent request decided the version, took the next baseline number or used the
        # same Idempotency-Key first. Nothing of this request was stored.
        session.rollback()
        raise DecisionInProgressError(
            "Another decision finished first. Reload the backlog to see where it stands."
        ) from error
    return view


def _response(view: DecisionView) -> DecisionResponse:
    decision = view.decision
    return DecisionResponse(
        id=decision.id,
        version_id=decision.version_id,
        decision=decision.decision,
        decided_by=decision.decided_by,
        revision=decision.revision,
        content_hash=decision.content_hash,
        decided_at=decision.decided_at,
        baseline_version=decision.baseline_number,
        current_baseline_id=None
        if view.current_baseline is None
        else view.current_baseline.version_id,
    )
