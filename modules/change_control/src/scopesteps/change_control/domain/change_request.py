"""A change request: one person's request to change the approved baseline, and where it stands.

Backlog versions, items and decisions are named by plain UUIDs here, because the backlog
module's typed ids come with its client, which domain code may not import.

The request, its text and the baseline it was made against are recorded before anything is
analysed. Analysis moves it on exactly once; the decision on its candidate moves it on again
(ADR 0011).
"""

import base64
import binascii
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from scopesteps.change_control.domain.ids import ChangeRequestId, ChangeSetId
from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import ConflictError, InvalidInputError
from scopesteps.projects.client import ProjectId


class ChangeRequestStatus(StrEnum):
    """Stored, and part of the API contract."""

    ANALYZING = "analyzing"
    IN_REVIEW = "in_review"
    """The analysis proposed a candidate, which waits for an approver."""
    NO_CHANGE_NEEDED = "no_change_needed"
    """The baseline already covers the request; nothing was proposed."""
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    """The analysis failed or was stopped before it proposed anything. Send the request again."""


ANALYSIS_OUTCOMES = frozenset(
    {
        ChangeRequestStatus.IN_REVIEW,
        ChangeRequestStatus.NO_CHANGE_NEEDED,
        ChangeRequestStatus.FAILED,
    }
)


class ChangeRequestStateError(ConflictError):
    code = "CHANGE_REQUEST_STATE_INVALID"


class InvalidCursorError(InvalidInputError):
    code = "INVALID_CURSOR"


@dataclass(frozen=True)
class ItemNote:
    """The agent's words about one item: why it changes, or how the change affects it."""

    item_id: UUID
    note: str


@dataclass(frozen=True)
class ScopeReversal:
    """A required scope decision on the candidate and what it would take back."""

    decision_id: UUID
    reverses: Literal["exclusion", "decision"]
    summary: str
    """The exclusion's summary, or the subject of the earlier decision."""
    reversed_decision_id: UUID | None = None


@dataclass(frozen=True)
class ChangeSummary:
    """How many baseline items the candidate adds, changes and removes, by stable id."""

    added: int
    changed: int
    removed: int


@dataclass(frozen=True)
class ScopeCount:
    """One kind of work before and after a change. `before` is unchanged + changed + removed and
    `after` is unchanged + changed + added."""

    before: int
    after: int
    added: int
    changed: int
    removed: int
    unchanged: int


@dataclass(frozen=True)
class ChangeImpact:
    """What a candidate does to the scope of its baseline, counted in code by stable ids."""

    epics: ScopeCount
    stories: ScopeCount
    criteria: ScopeCount
    scope_decisions: int
    """The decisions the change raised because it takes back an exclusion or earlier decision."""


@dataclass(frozen=True)
class ChangeAnalysis:
    """What a finished analysis recorded. `candidate_version_id` is None when no change is needed."""

    candidate_version_id: UUID | None
    analysis: str
    """The agent's summary of the request against the baseline, in its own words."""
    rationales: tuple[ItemNote, ...] = ()
    impacts: tuple[ItemNote, ...] = ()
    scope_reversals: tuple[ScopeReversal, ...] = ()


@dataclass(frozen=True)
class ChangeRequest:
    id: ChangeRequestId
    project_id: ProjectId
    number: int
    """1 for the project's first request, never reused: shown as CR-1."""
    text: str
    requested_by: UserId
    requested_by_name: str
    """Copied when the request is made, so the list reads the same after a rename."""
    requested_at: datetime
    base_version_id: UUID
    base_content_hash: str
    source_version_id: UUID
    """The request's text stored as an immutable source version, so the change can cite it."""
    run_id: UUID
    status: ChangeRequestStatus
    revision: int
    candidate_version_id: UUID | None = None
    change_set_id: ChangeSetId | None = None
    summary: ChangeSummary | None = None
    analysis: str | None = None
    rationales: tuple[ItemNote, ...] = ()
    impacts: tuple[ItemNote, ...] = ()
    scope_reversals: tuple[ScopeReversal, ...] = ()
    failure: str | None = None
    """The error code of a failed or stopped analysis."""
    analyzed_at: datetime | None = None

    def analyzed(
        self,
        analysis: ChangeAnalysis,
        summary: ChangeSummary | None,
        change_set_id: ChangeSetId | None,
        now: datetime,
    ) -> ChangeRequest:
        self._require_analyzing()
        has_candidate = analysis.candidate_version_id is not None
        return replace(
            self,
            status=(
                ChangeRequestStatus.IN_REVIEW
                if has_candidate
                else ChangeRequestStatus.NO_CHANGE_NEEDED
            ),
            revision=self.revision + 1,
            candidate_version_id=analysis.candidate_version_id,
            change_set_id=change_set_id if has_candidate else None,
            summary=summary if has_candidate else None,
            analysis=analysis.analysis,
            rationales=analysis.rationales,
            impacts=analysis.impacts,
            scope_reversals=analysis.scope_reversals,
            analyzed_at=now,
        )

    def failed(self, code: str, now: datetime) -> ChangeRequest:
        self._require_analyzing()
        return replace(
            self,
            status=ChangeRequestStatus.FAILED,
            revision=self.revision + 1,
            failure=code,
            analyzed_at=now,
        )

    def decided(self, *, approved: bool) -> ChangeRequest:
        """Its candidate was approved or rejected. When and by whom is on the decision."""
        if self.status is not ChangeRequestStatus.IN_REVIEW:
            raise ChangeRequestStateError(
                f"Change request CR-{self.number} is {self.status.value}, not in review",
                details={"status": self.status.value},
            )
        return replace(
            self,
            status=ChangeRequestStatus.APPROVED if approved else ChangeRequestStatus.REJECTED,
            revision=self.revision + 1,
        )

    def _require_analyzing(self) -> None:
        if self.status is not ChangeRequestStatus.ANALYZING:
            raise ChangeRequestStateError(
                f"Change request CR-{self.number} is already {self.status.value}",
                details={"status": self.status.value},
            )


@dataclass(frozen=True)
class ListCursor:
    """The last request of a page; the next page starts after it."""

    requested_at: datetime
    id: ChangeRequestId


def encode_cursor(cursor: ListCursor) -> str:
    raw = f"{cursor.requested_at.isoformat()}|{cursor.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(value: str) -> ListCursor:
    try:
        requested_at, _, request_id = base64.urlsafe_b64decode(value).decode().partition("|")
        cursor = ListCursor(datetime.fromisoformat(requested_at), ChangeRequestId(UUID(request_id)))
    except (ValueError, binascii.Error) as error:
        raise InvalidCursorError("The cursor is not one this list returned") from error
    if cursor.requested_at.tzinfo is None:
        raise InvalidCursorError("The cursor is not one this list returned")
    return cursor
