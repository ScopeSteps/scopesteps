"""Change request records with in-memory fakes: opening one, recording its analysis once, and
reading them back a page at a time."""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import pytest

from scopesteps.backlog.client import (
    BacklogVersion,
    BacklogVersionId,
    Criterion,
    CriterionId,
    Item,
    ItemId,
    VersionState,
    compare_versions,
)
from scopesteps.change_control.application.change_requests import (
    OpenChangeRequest,
    get_change_request,
    get_change_set,
    list_change_requests,
    measure_impact,
    open_change_request,
    record_analysis,
    record_failure,
)
from scopesteps.change_control.domain.change_request import (
    ChangeAnalysis,
    ChangeRequest,
    ChangeRequestStateError,
    ChangeRequestStatus,
    ItemNote,
    ListCursor,
    ScopeCount,
    ScopeReversal,
)
from scopesteps.change_control.domain.ids import ChangeRequestId
from scopesteps.identity.client import Actor, ProjectAccess, Role, UserId
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectId

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
PROJECT = ProjectId(UUID(int=1))
REQUESTER = Actor(UserId(UUID(int=2)), "Sample Editor")
EPIC = Item(ItemId(UUID(int=10)), "epic", None, "Booking", "Booking rooms.")
BOOK = Item(ItemId(UUID(int=11)), "story", EPIC.id, "Book a room", "Book.")
CANCEL = Item(ItemId(UUID(int=12)), "story", EPIC.id, "Cancel", "Cancel.")


def _version(number: int, *items: Item, state: VersionState) -> BacklogVersion:
    return BacklogVersion(
        id=BacklogVersionId(UUID(int=100 + number)),
        project_id=PROJECT,
        base_version_id=None,
        revision=1,
        state=state,
        content_hash=str(number) * 64,
        run_id=None,
        source_version_ids=(),
        items=items,
        decisions=(),
        out_of_scope=(),
        created_by=REQUESTER.user_id,
        created_at=NOW,
    )


BASE = _version(1, EPIC, BOOK, CANCEL, state=VersionState.APPROVED)
CANDIDATE = _version(
    2,
    EPIC,
    replace(BOOK, title="Book a room or a series"),
    Item(ItemId(UUID(int=13)), "story", EPIC.id, "Book a series", "Weekly."),
    state=VersionState.IN_REVIEW,
)


@dataclass
class FakeRequests:
    rows: dict[ChangeRequestId, ChangeRequest] = field(
        default_factory=dict[ChangeRequestId, ChangeRequest]
    )

    def get(self, request_id: ChangeRequestId) -> ChangeRequest | None:
        return self.rows.get(request_id)

    def by_run(self, run_id: UUID) -> ChangeRequest | None:
        return next((r for r in self.rows.values() if r.run_id == run_id), None)

    def by_candidate(self, version_id: BacklogVersionId) -> ChangeRequest | None:
        return next((r for r in self.rows.values() if r.candidate_version_id == version_id), None)

    def next_number(self, project_id: ProjectId) -> int:
        return 1 + max((r.number for r in self.rows.values()), default=0)

    def add(self, request: ChangeRequest) -> None:
        self.rows[request.id] = request

    def save(self, request: ChangeRequest, *, expected_revision: int) -> bool:
        if self.rows[request.id].revision != expected_revision:
            return False
        self.rows[request.id] = request
        return True

    def newest_first(
        self, project_id: ProjectId, *, after: ListCursor | None, limit: int
    ) -> list[ChangeRequest]:
        ordered = sorted(self.rows.values(), key=lambda r: (r.requested_at, r.id), reverse=True)
        if after is not None:
            ordered = [
                r for r in ordered if (r.requested_at, r.id) < (after.requested_at, after.id)
            ]
        return ordered[:limit]


@dataclass
class FakeVersions:
    versions: dict[UUID, BacklogVersion]

    def load(self, version_id: UUID) -> BacklogVersion | None:
        return self.versions.get(version_id)

    def baseline_numbers(self, version_ids: Sequence[UUID]) -> dict[UUID, int]:
        return {BASE.id: 1} if BASE.id in version_ids else {}


VERSIONS = FakeVersions({BASE.id: BASE, CANDIDATE.id: CANDIDATE})


def _open(store: FakeRequests, run: int, at: datetime = NOW) -> ChangeRequest:
    return open_change_request(
        store,
        OpenChangeRequest(
            project_id=PROJECT,
            text="Add weekly bookings.",
            requested_by=REQUESTER.user_id,
            requested_by_name=REQUESTER.display_name,
            base_version_id=BASE.id,
            base_content_hash=BASE.content_hash,
            source_version_id=UUID(int=50),
            run_id=UUID(int=run),
        ),
        at,
    )


def _access(*roles: Role) -> ProjectAccess:
    return ProjectAccess(actor=REQUESTER, project_id=PROJECT, roles=frozenset(roles))


def test_a_request_is_numbered_and_analysing_until_its_run_reports() -> None:
    store = FakeRequests()

    first, second = _open(store, 1), _open(store, 2)

    assert (first.number, second.number) == (1, 2)
    assert first.status is ChangeRequestStatus.ANALYZING


def test_the_summary_is_counted_from_stable_ids_not_taken_from_the_model() -> None:
    store = FakeRequests()
    _open(store, 1)

    recorded = record_analysis(
        store,
        VERSIONS,
        UUID(int=1),
        ChangeAnalysis(CANDIDATE.id, "Adds a series.", rationales=(ItemNote(BOOK.id, "Why"),)),
        NOW,
    )

    assert recorded.status is ChangeRequestStatus.IN_REVIEW
    assert recorded.summary is not None
    assert (recorded.summary.added, recorded.summary.changed, recorded.summary.removed) == (1, 1, 1)
    assert recorded.change_set_id is not None


def test_an_analysis_is_recorded_once() -> None:
    store = FakeRequests()
    _open(store, 1)
    record_analysis(store, VERSIONS, UUID(int=1), ChangeAnalysis(None, "Covered."), NOW)

    with pytest.raises(ChangeRequestStateError):
        record_analysis(store, VERSIONS, UUID(int=1), ChangeAnalysis(None, "Again."), NOW)
    assert record_failure(store, UUID(int=1), "RUN_CANCELLED", NOW) is None
    stored = store.by_run(UUID(int=1))
    assert stored is not None
    assert stored.status is ChangeRequestStatus.NO_CHANGE_NEEDED


def test_a_failed_analysis_keeps_its_error_code() -> None:
    store = FakeRequests()
    _open(store, 1)

    failed = record_failure(store, UUID(int=1), "RUN_CANCELLED", NOW)

    assert failed is not None
    assert (failed.status, failed.failure) == (ChangeRequestStatus.FAILED, "RUN_CANCELLED")


def test_members_page_through_requests_newest_first() -> None:
    store = FakeRequests()
    for n in range(3):
        _open(store, n + 1, NOW + timedelta(minutes=n))

    first = list_change_requests(store, VERSIONS, _access(Role.VIEWER), limit=2, cursor=None)
    rest = list_change_requests(
        store, VERSIONS, _access(Role.VIEWER), limit=2, cursor=first.next_cursor
    )

    assert [r.request.number for r in first.requests] == [3, 2]
    assert [r.request.number for r in rest.requests] == [1]
    assert rest.next_cursor is None
    assert first.requests[0].base_version_number == 1
    with pytest.raises(NotFoundError):
        list_change_requests(store, VERSIONS, _access(), limit=2, cursor=None)


def test_only_a_proposed_candidate_has_a_change_set() -> None:
    store = FakeRequests()
    _open(store, 1)
    record_analysis(store, VERSIONS, UUID(int=1), ChangeAnalysis(CANDIDATE.id, "Adds."), NOW)

    change_set = get_change_set(store, VERSIONS, lambda _: _access(Role.VIEWER), CANDIDATE.id)

    assert [c.kind for c in change_set.changes] == ["modify_item", "add_item", "remove_item"]
    with pytest.raises(NotFoundError):
        get_change_set(store, VERSIONS, lambda _: _access(Role.VIEWER), BASE.id)
    with pytest.raises(NotFoundError):
        get_change_set(store, VERSIONS, lambda _: _access(), CANDIDATE.id)


def _criterion(
    n: int, text: str, suggestion: Literal["pending", "rejected"] | None = None
) -> Criterion:
    return Criterion(
        CriterionId(UUID(int=200 + n)),
        text,
        "proposed" if suggestion else "source",
        suggestion=suggestion,
    )


def test_the_impact_counts_each_kind_of_work_from_the_stable_id_comparison() -> None:
    kept, edited, dropped = _criterion(1, "Kept"), _criterion(2, "Edited"), _criterion(3, "Dropped")
    base = replace(
        BASE,
        items=(
            EPIC,
            replace(BOOK, criteria=(kept, edited, dropped)),
            replace(CANCEL, criteria=(kept,)),
        ),
    )
    book = replace(
        BOOK, criteria=(kept, replace(edited, text="Edited again"), _criterion(4, "New"))
    )
    series = Item(
        ItemId(UUID(int=13)), "story", EPIC.id, "Series", "Weekly.", (_criterion(5, "W"),)
    )
    candidate = replace(CANDIDATE, items=(EPIC, book, series))
    changes = compare_versions(base, candidate)

    impact = measure_impact(base, candidate, changes, scope_decisions=1)

    assert impact.epics == ScopeCount(before=1, after=1, added=0, changed=0, removed=0, unchanged=1)
    assert impact.stories == ScopeCount(
        before=2, after=2, added=1, changed=1, removed=1, unchanged=0
    )
    # Book keeps one criterion, edits one, drops one and gains one; Cancel's goes with it;
    # Series brings its own.
    assert impact.criteria == ScopeCount(
        before=4, after=4, added=2, changed=1, removed=2, unchanged=1
    )
    assert impact.scope_decisions == 1


def test_a_rejected_suggestion_is_left_out_as_approval_would_leave_it_out() -> None:
    pending, rejected = _criterion(1, "Maybe", "pending"), _criterion(2, "No", "rejected")
    candidate = replace(
        CANDIDATE, items=(EPIC, replace(BOOK, criteria=(pending, rejected)), CANCEL)
    )

    impact = measure_impact(BASE, candidate, compare_versions(BASE, candidate), scope_decisions=0)

    assert (impact.criteria.before, impact.criteria.after, impact.criteria.added) == (0, 1, 1)


def test_an_item_that_changes_kind_leaves_one_kind_and_joins_the_other() -> None:
    candidate = replace(CANDIDATE, items=(replace(EPIC, kind="story"), BOOK, CANCEL))

    impact = measure_impact(BASE, candidate, compare_versions(BASE, candidate), scope_decisions=0)

    assert (impact.epics.before, impact.epics.removed, impact.epics.after) == (1, 1, 0)
    assert (impact.stories.before, impact.stories.added, impact.stories.after) == (2, 1, 3)
    assert impact.stories.unchanged == 2


def test_a_request_reads_its_impact_and_summary_from_the_versions_not_the_analysis() -> None:
    store = FakeRequests()
    request = _open(store, 1)
    reversal = ScopeReversal(UUID(int=300), "exclusion", "No recurring bookings")
    record_analysis(
        store,
        VERSIONS,
        UUID(int=1),
        ChangeAnalysis(CANDIDATE.id, "Adds a series.", scope_reversals=(reversal,)),
        NOW,
    )
    # The candidate as it stands now: an approver may have rejected a suggestion since.
    store.rows[request.id] = replace(store.rows[request.id], summary=None)

    listed = get_change_request(store, VERSIONS, lambda _: _access(Role.VIEWER), request.id)

    assert listed.summary is not None
    assert (listed.summary.added, listed.summary.changed, listed.summary.removed) == (1, 1, 1)
    assert listed.impact is not None
    assert listed.impact.stories == ScopeCount(
        before=2, after=2, added=1, changed=1, removed=1, unchanged=0
    )
    assert listed.impact.scope_decisions == 1


def test_a_request_without_a_candidate_has_no_impact() -> None:
    store = FakeRequests()
    request = _open(store, 1)
    record_analysis(store, VERSIONS, UUID(int=1), ChangeAnalysis(None, "Covered."), NOW)

    listed = get_change_request(store, VERSIONS, lambda _: _access(Role.VIEWER), request.id)

    assert (listed.summary, listed.impact) == (None, None)
