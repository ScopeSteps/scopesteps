"""What other modules may use of change control: its ids, the change request records the
agent's change runs open and report on in their own transactions (ADR 0011), what a change does
to the scope, and the port a decided change is reported through."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from scopesteps.change_control.application import change_requests
from scopesteps.change_control.application.change_requests import OpenChangeRequest
from scopesteps.change_control.application.decisions import ChangeOutcome, ChangeOutcomeRecorder
from scopesteps.change_control.domain.change_request import (
    ChangeAnalysis,
    ChangeImpact,
    ChangeRequestStatus,
    ChangeSummary,
    ItemNote,
    ScopeCount,
    ScopeReversal,
)
from scopesteps.change_control.domain.ids import ApprovalId, ChangeRequestId, ChangeSetId
from scopesteps.change_control.infrastructure.repository import (
    BacklogVersionReader,
    SqlChangeRequestStore,
)
from scopesteps.projects.client import ProjectId


@dataclass(frozen=True)
class ChangeRequestRef:
    id: ChangeRequestId
    number: int
    """Shown as CR-1, CR-2, ..."""


def open_change_request(
    session: Session, command: OpenChangeRequest, now: datetime
) -> ChangeRequestRef:
    """Record a change request about to be analysed, in the caller's transaction, as
    `analyzing`. Performs no access check and records no audit event: the caller has checked
    both the actor and the baseline, and records the action. A concurrent request that took the
    same number fails the caller's transaction with the database's integrity error."""
    request = change_requests.open_change_request(SqlChangeRequestStore(session), command, now)
    return ChangeRequestRef(request.id, request.number)


def record_change_analysis(
    session: Session, run_id: UUID, analysis: ChangeAnalysis, now: datetime
) -> ChangeSummary | None:
    """Record the analysis of the run's request in the caller's transaction: `in_review` with
    the saved candidate, or `no_change_needed` without one. Returns the counts of a stable-id
    comparison of the candidate with the baseline. Raises if the request is not `analyzing`."""
    return change_requests.record_analysis(
        SqlChangeRequestStore(session), BacklogVersionReader(session), run_id, analysis, now
    ).summary


def record_change_failure(session: Session, run_id: UUID, code: str, now: datetime) -> None:
    """Mark the run's request `failed` with the run's error code, in the caller's transaction.
    Does nothing if the run analysed no request or its request was already decided."""
    change_requests.record_failure(SqlChangeRequestStore(session), run_id, code, now)


class ScopeCountResponse(BaseModel):
    """One kind of work before and after the change. `before` is unchanged + changed + removed;
    `after` is unchanged + changed + added."""

    before: int
    after: int
    added: int
    changed: int
    removed: int
    unchanged: int


class ChangeImpactResponse(BaseModel):
    """What the candidate does to the baseline's scope, counted in code from the stable-id
    comparison of the two versions, never by the model. A criterion counts as changed when its
    text or evidence differs; an item, when any of its fields or criteria do."""

    epics: ScopeCountResponse
    stories: ScopeCountResponse
    criteria: ScopeCountResponse
    scope_decisions: int = Field(
        description="Scope decisions the change raised: earlier exclusions or decisions it "
        "would take back, which an approver must settle."
    )


def impact_response(impact: ChangeImpact) -> ChangeImpactResponse:
    def count(scope: ScopeCount) -> ScopeCountResponse:
        return ScopeCountResponse(
            before=scope.before,
            after=scope.after,
            added=scope.added,
            changed=scope.changed,
            removed=scope.removed,
            unchanged=scope.unchanged,
        )

    return ChangeImpactResponse(
        epics=count(impact.epics),
        stories=count(impact.stories),
        criteria=count(impact.criteria),
        scope_decisions=impact.scope_decisions,
    )


def load_change_impacts(
    session: Session, request_ids: Collection[UUID]
) -> dict[ChangeRequestId, ChangeImpact]:
    """The current impact of each request among `request_ids` that has a candidate; others are
    absent. Performs no access check: the caller shows only requests of a project the actor is a
    member of."""
    return change_requests.load_impacts(
        SqlChangeRequestStore(session), BacklogVersionReader(session), request_ids
    )


def in_review_counts(session: Session, project_ids: Collection[ProjectId]) -> dict[ProjectId, int]:
    """For each project given, the change requests whose candidate waits for an approver, in one
    query; projects with none are absent. Performs no access check."""
    return SqlChangeRequestStore(session).in_review_counts(project_ids)


def get_change_outcome_recorder() -> ChangeOutcomeRecorder:
    """FastAPI dependency the approve and reject routes report a decided change through.

    The conversation belongs to `agent`, which builds on this module, so it cannot be imported
    here; the composition root binds the agent's recorder with `app.dependency_overrides`.
    """
    raise RuntimeError("get_change_outcome_recorder is not bound to the agent's conversation")


__all__ = [
    "ApprovalId",
    "ChangeAnalysis",
    "ChangeImpact",
    "ChangeImpactResponse",
    "ChangeOutcome",
    "ChangeOutcomeRecorder",
    "ChangeRequestId",
    "ChangeRequestRef",
    "ChangeRequestStatus",
    "ChangeSetId",
    "ChangeSummary",
    "ItemNote",
    "OpenChangeRequest",
    "ScopeCount",
    "ScopeCountResponse",
    "ScopeReversal",
    "get_change_outcome_recorder",
    "impact_response",
    "in_review_counts",
    "load_change_impacts",
    "open_change_request",
    "record_change_analysis",
    "record_change_failure",
]
