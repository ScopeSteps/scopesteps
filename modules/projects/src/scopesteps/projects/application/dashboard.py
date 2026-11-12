"""A project's dashboard: where its scope stands, what is stuck and who it waits on.

Every figure is read from what the app already stores, so each matches the page it comes from:
counts from the backlog, change requests from their page, waiting per person as the Team page
counts it. Waiting times and averages come from stored timestamps and the activity log. No AI.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.backlog.client import BacklogOutline, BacklogVersionId, ScopeStatus
from scopesteps.identity.client import DirectoryMember, ProjectAccess, Role
from scopesteps.projects.client import (
    DashboardApproval,
    DashboardChangeRequest,
    DashboardCoverage,
    DashboardQuestion,
)

MAX_LISTED_QUESTIONS = 5
"""The oldest open questions the dashboard names; the rest are counted. Enough to see what is
stuck without repeating the chat."""

CHANGE_REQUEST_STATUSES = (
    "analyzing",
    "in_review",
    "no_change_needed",
    "approved",
    "rejected",
    "failed",
)


class DashboardSources(Protocol):
    """Reads for one project, in the request's transaction. None check access."""

    def status(self) -> ScopeStatus: ...

    def outline(self, version_id: BacklogVersionId) -> BacklogOutline | None: ...

    def run_of(self, version_id: BacklogVersionId) -> UUID | None:
        """The agent run that proposed the version."""
        ...

    def coverage(self, run_id: UUID) -> DashboardCoverage | None: ...

    def open_questions(self) -> Sequence[DashboardQuestion]: ...

    def asked_at(self) -> Mapping[UUID, datetime]:
        """When the agent asked each question, from the activity log."""
        ...

    def approvals(self) -> Sequence[DashboardApproval]: ...

    def change_requests(self) -> Sequence[DashboardChangeRequest]: ...

    def members(self) -> Sequence[DirectoryMember]: ...

    def waiting_by_role(self) -> Mapping[Role, int]: ...

    def display_names(self, user_ids: Sequence[UUID]) -> Mapping[UUID, str]: ...


@dataclass(frozen=True)
class ItemCounts:
    version_id: BacklogVersionId
    approved: bool
    """False when no version is approved yet and the counts are the draft's."""
    epics: int
    stories: int
    tasks: int


@dataclass(frozen=True)
class Coverage:
    version_number: int | None
    """The approved version whose drafting run measured it; None for a draft in progress."""
    confirmed: int
    covered: int


@dataclass(frozen=True)
class WaitingQuestion:
    id: UUID
    subject: str
    asked_at: datetime | None
    waited_seconds: int | None


@dataclass(frozen=True)
class OpenQuestions:
    count: int
    oldest: tuple[WaitingQuestion, ...]
    """At most `MAX_LISTED_QUESTIONS`, longest waiting first; a question the log has no time for
    comes last."""


@dataclass(frozen=True)
class ChangeRequestFigures:
    total: int
    by_status: Mapping[str, int]
    """Every status in `CHANGE_REQUEST_STATUSES`, zero included."""
    decided: int
    average_seconds_to_decision: int | None
    """From sending a request to an approver approving or rejecting what it proposed; None
    until one is decided."""


@dataclass(frozen=True)
class WaitingOn:
    user_id: UUID
    display_name: str
    role: Role
    waiting: int


@dataclass(frozen=True)
class TimelineEntry:
    version_id: UUID
    number: int
    approved_by: UUID
    approved_by_name: str
    approved_at: datetime
    change_request_number: int | None


@dataclass(frozen=True)
class Dashboard:
    status: ScopeStatus
    has_sources: bool
    counts: ItemCounts | None
    coverage: Coverage | None
    open_questions: OpenQuestions
    change_requests: ChangeRequestFigures
    waiting_on: tuple[WaitingOn, ...]
    """Members something waits for, most first, then by name."""
    timeline: tuple[TimelineEntry, ...]
    """Approved versions, oldest first."""


def project_dashboard(
    sources: DashboardSources, access: ProjectAccess, *, has_sources: bool, now: datetime
) -> Dashboard:
    """Any member may read it; a non-member gets the same not-found as a missing project."""
    access.require_member()
    status = sources.status()
    approvals = sources.approvals()
    return Dashboard(
        status=status,
        has_sources=has_sources,
        counts=_counts(sources, status),
        coverage=_coverage(sources, status, approvals),
        open_questions=_open_questions(sources, now),
        change_requests=change_request_figures(sources.change_requests()),
        waiting_on=_waiting_on(sources),
        timeline=_timeline(sources, approvals),
    )


def _counts(sources: DashboardSources, status: ScopeStatus) -> ItemCounts | None:
    approved = status.baseline_version_id is not None
    version_id = status.baseline_version_id or status.open_version_id
    outline = None if version_id is None else sources.outline(version_id)
    if outline is None:
        return None
    stories = [item for item in outline.items if item.kind == "story"]
    return ItemCounts(
        version_id=outline.version_id,
        approved=approved,
        epics=sum(item.kind == "epic" for item in outline.items),
        stories=len(stories),
        tasks=sum(len(story.tasks) for story in stories),
    )


def _coverage(
    sources: DashboardSources, status: ScopeStatus, approvals: Sequence[DashboardApproval]
) -> Coverage | None:
    """From the newest approved version an initial run drafted; a version made by a change
    request has no coverage of its own. Without an approved version, the draft in progress."""
    candidates: list[tuple[BacklogVersionId, int | None]] = [
        (BacklogVersionId(approval.version_id), approval.number) for approval in reversed(approvals)
    ]
    if not candidates and status.open_version_id is not None:
        candidates.append((status.open_version_id, None))
    for version_id, number in candidates:
        run_id = sources.run_of(version_id)
        found = None if run_id is None else sources.coverage(run_id)
        if found is not None:
            return Coverage(number, found.confirmed, found.covered)
    return None


def _open_questions(sources: DashboardSources, now: datetime) -> OpenQuestions:
    questions = sources.open_questions()
    asked: Mapping[UUID, datetime] = sources.asked_at() if questions else {}
    waiting = [
        WaitingQuestion(
            id=question.id,
            subject=question.subject,
            asked_at=asked.get(question.id),
            waited_seconds=None
            if question.id not in asked
            else max(0, int((now - asked[question.id]).total_seconds())),
        )
        for question in questions
    ]
    waiting.sort(key=lambda q: (q.asked_at is None, q.asked_at or now, str(q.id)))
    return OpenQuestions(len(waiting), tuple(waiting[:MAX_LISTED_QUESTIONS]))


def change_request_figures(requests: Sequence[DashboardChangeRequest]) -> ChangeRequestFigures:
    statuses = Counter(request.status for request in requests)
    waits = [
        (request.decided_at - request.requested_at).total_seconds()
        for request in requests
        if request.decided_at is not None
    ]
    return ChangeRequestFigures(
        total=len(requests),
        by_status={status: statuses.get(status, 0) for status in CHANGE_REQUEST_STATUSES},
        decided=len(waits),
        average_seconds_to_decision=round(sum(waits) / len(waits)) if waits else None,
    )


def _waiting_on(sources: DashboardSources) -> tuple[WaitingOn, ...]:
    by_role = sources.waiting_by_role()
    people = [
        WaitingOn(member.user_id, member.display_name, member.role, by_role.get(member.role, 0))
        for member in sources.members()
    ]
    people = [person for person in people if person.waiting > 0]
    people.sort(key=lambda person: (-person.waiting, person.display_name.casefold()))
    return tuple(people)


def _timeline(
    sources: DashboardSources, approvals: Sequence[DashboardApproval]
) -> tuple[TimelineEntry, ...]:
    names = sources.display_names(list({approval.approved_by for approval in approvals}))
    return tuple(
        TimelineEntry(
            version_id=approval.version_id,
            number=approval.number,
            approved_by=approval.approved_by,
            approved_by_name=names.get(approval.approved_by, "Former member"),
            approved_at=approval.approved_at,
            change_request_number=approval.change_request_number,
        )
        for approval in approvals
    )
