from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

# Loaded first, as the app loads it: identity's client and this one import each other.
import scopesteps.projects.client  # noqa: F401  # pyright: ignore[reportUnusedImport]
from scopesteps.backlog.client import (
    BacklogOutline,
    BacklogVersionId,
    OutlineItem,
    ScopeState,
    ScopeStatus,
    VersionState,
)
from scopesteps.identity.client import Actor, DirectoryMember, ProjectAccess, Role, UserId
from scopesteps.kernel.errors import NotFoundError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.application.dashboard import (
    MAX_LISTED_QUESTIONS,
    change_request_figures,
    project_dashboard,
)
from scopesteps.projects.client import (
    DashboardApproval,
    DashboardChangeRequest,
    DashboardCoverage,
    DashboardQuestion,
    ProjectId,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
PROJECT = ProjectId(new_id())
ANA, BEN, CAL = UserId(new_id()), UserId(new_id()), UserId(new_id())
V1, V2 = BacklogVersionId(new_id()), BacklogVersionId(new_id())
RUN_1 = new_id()


def _outline(version_id: BacklogVersionId, stories: int, tasks_each: int) -> BacklogOutline:
    epic = OutlineItem("epic", "Room booking", "", (), None)
    story = OutlineItem("story", "Book", "", (), "Room booking", tasks=("t",) * tasks_each)
    return BacklogOutline(version_id, VersionState.APPROVED, (epic, *([story] * stories)), ())


@dataclass
class FakeSources:
    scope: ScopeStatus = field(default_factory=lambda: ScopeStatus(ScopeState.NO_BASELINE))
    outlines: dict[BacklogVersionId, BacklogOutline] = field(
        default_factory=dict[BacklogVersionId, BacklogOutline]
    )
    runs: dict[BacklogVersionId, UUID] = field(default_factory=dict[BacklogVersionId, UUID])
    coverages: dict[UUID, DashboardCoverage] = field(default_factory=dict[UUID, DashboardCoverage])
    questions: list[DashboardQuestion] = field(default_factory=list[DashboardQuestion])
    asked: dict[UUID, datetime] = field(default_factory=dict[UUID, datetime])
    approved: list[DashboardApproval] = field(default_factory=list[DashboardApproval])
    requests: list[DashboardChangeRequest] = field(default_factory=list[DashboardChangeRequest])
    people: list[DirectoryMember] = field(default_factory=list[DirectoryMember])
    by_role: dict[Role, int] = field(default_factory=dict[Role, int])
    names: dict[UUID, str] = field(default_factory=dict[UUID, str])

    def status(self) -> ScopeStatus:
        return self.scope

    def outline(self, version_id: BacklogVersionId) -> BacklogOutline | None:
        return self.outlines.get(version_id)

    def run_of(self, version_id: BacklogVersionId) -> UUID | None:
        return self.runs.get(version_id)

    def coverage(self, run_id: UUID) -> DashboardCoverage | None:
        return self.coverages.get(run_id)

    def open_questions(self) -> Sequence[DashboardQuestion]:
        return self.questions

    def asked_at(self) -> Mapping[UUID, datetime]:
        return self.asked

    def approvals(self) -> Sequence[DashboardApproval]:
        return self.approved

    def change_requests(self) -> Sequence[DashboardChangeRequest]:
        return self.requests

    def members(self) -> Sequence[DirectoryMember]:
        return self.people

    def waiting_by_role(self) -> Mapping[Role, int]:
        return self.by_role

    def display_names(self, user_ids: Sequence[UUID]) -> Mapping[UUID, str]:
        return {user_id: self.names[user_id] for user_id in user_ids if user_id in self.names}


def _access(role: Role | None = Role.VIEWER) -> ProjectAccess:
    return ProjectAccess(Actor(ANA, "Ana"), PROJECT, role)


def _approved_twice() -> FakeSources:
    """v1 drafted by an initial run, v2 approved from change request 1."""
    return FakeSources(
        scope=ScopeStatus(ScopeState.BASELINE, 2, V2),
        outlines={V2: _outline(V2, stories=3, tasks_each=2)},
        runs={V1: RUN_1, V2: new_id()},
        coverages={RUN_1: DashboardCoverage(confirmed=10, covered=9)},
        approved=[
            DashboardApproval(V1, 1, BEN, NOW - timedelta(days=10), None),
            DashboardApproval(V2, 2, CAL, NOW - timedelta(days=2), 1),
        ],
        names={BEN: "Ben Approver"},
    )


def test_counts_are_the_approved_versions_with_its_written_and_accepted_tasks() -> None:
    found = project_dashboard(_approved_twice(), _access(), has_sources=True, now=NOW)

    assert found.counts is not None
    assert (found.counts.version_id, found.counts.approved) == (V2, True)
    assert (found.counts.epics, found.counts.stories, found.counts.tasks) == (1, 3, 6)


def test_counts_fall_back_to_the_draft_before_anything_is_approved() -> None:
    sources = FakeSources(
        scope=ScopeStatus(ScopeState.DRAFT_IN_PROGRESS, open_version_id=V1),
        outlines={V1: _outline(V1, stories=2, tasks_each=0)},
    )

    found = project_dashboard(sources, _access(), has_sources=True, now=NOW)

    assert found.counts is not None
    assert (found.counts.approved, found.counts.stories) == (False, 2)


def test_coverage_comes_from_the_newest_approved_version_an_initial_run_drafted() -> None:
    found = project_dashboard(_approved_twice(), _access(), has_sources=True, now=NOW)

    assert found.coverage is not None
    assert (found.coverage.version_number, found.coverage.confirmed, found.coverage.covered) == (
        1,
        10,
        9,
    )


def test_the_timeline_lists_every_approval_oldest_first_with_names() -> None:
    found = project_dashboard(_approved_twice(), _access(), has_sources=True, now=NOW)

    assert [(entry.number, entry.approved_by_name) for entry in found.timeline] == [
        (1, "Ben Approver"),
        (2, "Former member"),
    ]
    assert found.timeline[1].change_request_number == 1
    assert found.timeline[1].approved_at == NOW - timedelta(days=2)


def test_open_questions_list_the_longest_waiting_first_with_waits_from_the_log() -> None:
    questions = [DashboardQuestion(new_id(), f"Question {n}") for n in range(7)]
    asked = {q.id: NOW - timedelta(hours=n + 1) for n, q in enumerate(questions[:6])}
    sources = FakeSources(questions=questions, asked=asked)

    found = project_dashboard(sources, _access(), has_sources=True, now=NOW)

    assert found.open_questions.count == 7
    assert len(found.open_questions.oldest) == MAX_LISTED_QUESTIONS
    oldest = found.open_questions.oldest[0]
    assert (oldest.subject, oldest.waited_seconds) == ("Question 5", 6 * 3600)
    assert [q.waited_seconds for q in found.open_questions.oldest] == [
        6 * 3600,
        5 * 3600,
        4 * 3600,
        3 * 3600,
        2 * 3600,
    ]


def test_a_question_the_log_has_no_time_for_comes_last_without_a_wait() -> None:
    logged, unlogged = DashboardQuestion(new_id(), "Logged"), DashboardQuestion(new_id(), "Not")
    sources = FakeSources(questions=[unlogged, logged], asked={logged.id: NOW - timedelta(days=1)})

    found = project_dashboard(sources, _access(), has_sources=True, now=NOW)

    assert [(q.subject, q.waited_seconds) for q in found.open_questions.oldest] == [
        ("Logged", 86400),
        ("Not", None),
    ]


def test_change_requests_count_every_status_and_average_only_decided_ones() -> None:
    sent = NOW - timedelta(days=10)
    requests = [
        DashboardChangeRequest(1, "approved", sent, sent + timedelta(days=1)),
        DashboardChangeRequest(2, "rejected", sent, sent + timedelta(days=3)),
        DashboardChangeRequest(3, "in_review", sent, None),
        DashboardChangeRequest(4, "failed", sent, None),
    ]

    figures = change_request_figures(requests)

    assert figures.total == 4
    assert figures.by_status == {
        "analyzing": 0,
        "in_review": 1,
        "no_change_needed": 0,
        "approved": 1,
        "rejected": 1,
        "failed": 1,
    }
    assert (figures.decided, figures.average_seconds_to_decision) == (2, 2 * 86400)


def test_no_decided_change_request_means_no_average() -> None:
    assert change_request_figures([]).average_seconds_to_decision is None


def test_waiting_on_names_members_by_their_roles_waiting_most_first() -> None:
    sources = FakeSources(
        people=[
            DirectoryMember(BEN, "ben", Role.EDITOR),
            DirectoryMember(ANA, "Ana", Role.APPROVER),
            DirectoryMember(CAL, "Cal", Role.VIEWER),
        ],
        by_role={Role.APPROVER: 3, Role.EDITOR: 2, Role.VIEWER: 0},
    )

    found = project_dashboard(sources, _access(), has_sources=True, now=NOW)

    assert [(p.display_name, p.waiting) for p in found.waiting_on] == [("Ana", 3), ("ben", 2)]


def test_a_new_project_has_nothing_to_show() -> None:
    found = project_dashboard(FakeSources(), _access(), has_sources=False, now=NOW)

    assert (found.has_sources, found.counts, found.coverage, found.timeline) == (
        False,
        None,
        None,
        (),
    )
    assert found.open_questions.count == 0


def test_a_non_member_is_told_the_project_does_not_exist() -> None:
    with pytest.raises(NotFoundError):
        project_dashboard(FakeSources(), _access(None), has_sources=True, now=NOW)
