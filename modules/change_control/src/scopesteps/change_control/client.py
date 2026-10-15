"""What other modules may use of change control: its ids, and the change request records the
agent's change runs open and report on in their own transactions (ADR 0011)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from scopesteps.change_control.application import change_requests
from scopesteps.change_control.application.change_requests import OpenChangeRequest
from scopesteps.change_control.domain.change_request import (
    ChangeAnalysis,
    ChangeRequestStatus,
    ChangeSummary,
    ItemNote,
    ScopeReversal,
)
from scopesteps.change_control.domain.ids import ApprovalId, ChangeRequestId, ChangeSetId
from scopesteps.change_control.infrastructure.repository import (
    BacklogVersionReader,
    SqlChangeRequestStore,
)


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


__all__ = [
    "ApprovalId",
    "ChangeAnalysis",
    "ChangeRequestId",
    "ChangeRequestRef",
    "ChangeRequestStatus",
    "ChangeSetId",
    "ChangeSummary",
    "ItemNote",
    "OpenChangeRequest",
    "ScopeReversal",
    "open_change_request",
    "record_change_analysis",
    "record_change_failure",
]
