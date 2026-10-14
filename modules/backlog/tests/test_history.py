import base64
from collections.abc import Collection, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from scopesteps.backlog.application.history import list_versions
from scopesteps.backlog.domain.history import (
    InvalidCursorError,
    ListCursor,
    VersionListing,
    compare_items,
    decode_cursor,
    encode_cursor,
)
from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, ItemId
from scopesteps.backlog.domain.version import Criterion, Evidence, Item, VersionState
from scopesteps.backlog.domain.version_decision import DecisionReader, VersionDecision
from scopesteps.identity.client import Actor, ProjectAccess, Role, UserId
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectId

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
EDITOR = UserId(UUID(int=7))
PROJECT = ProjectId(UUID(int=9))
SOURCED = Criterion(
    CriterionId(UUID(int=10)),
    "A student books one slot.",
    "source",
    (Evidence(UUID(int=1), UUID(int=2)),),
)
SUGGESTED = Criterion(
    CriterionId(UUID(int=11)), "A confirmation is shown.", "proposed", suggestion="accepted"
)
EPIC = Item(ItemId(UUID(int=20)), "epic", None, "Room booking", "Booking rooms.")
STORY = Item(
    ItemId(UUID(int=21)), "story", EPIC.id, "Book a room", "As a student.", (SOURCED, SUGGESTED)
)
OTHER = Item(ItemId(UUID(int=22)), "story", EPIC.id, "Cancel a booking", "As a student.")


def test_identical_versions_have_no_changes() -> None:
    assert compare_items((EPIC, STORY), (EPIC, STORY)) == ()


def test_items_are_matched_by_id_not_by_title() -> None:
    renamed = replace(STORY, title="Book a study room")

    (change,) = compare_items((EPIC, STORY), (EPIC, renamed))

    assert (change.kind, change.item_id, change.changed_fields) == (
        "modify_item",
        STORY.id,
        ("title",),
    )
    assert (change.before, change.after, change.criteria) == (STORY, renamed, ())


def test_added_and_removed_items_are_reported_in_order() -> None:
    changes = compare_items((EPIC, STORY), (EPIC, OTHER))

    assert [(c.kind, c.item_id) for c in changes] == [
        ("add_item", OTHER.id),
        ("remove_item", STORY.id),
    ]
    assert (changes[0].before, changes[0].after) == (None, OTHER)
    assert (changes[1].before, changes[1].after) == (STORY, None)


def test_criteria_are_matched_by_their_stable_ids() -> None:
    added = Criterion(CriterionId(UUID(int=12)), "Rooms show capacity.", "person")
    edited = replace(SOURCED, text="A signed-in student books one slot.")
    after = replace(STORY, criteria=(edited, added))

    (change,) = compare_items((EPIC, STORY), (EPIC, after))

    assert change.changed_fields == ()
    assert [(c.kind, c.criterion_id) for c in change.criteria] == [
        ("modified", SOURCED.id),
        ("added", added.id),
        ("removed", SUGGESTED.id),
    ]
    assert (change.criteria[0].before, change.criteria[0].after) == (SOURCED, edited)


def test_a_moved_story_is_a_modification_of_its_parent() -> None:
    other_epic = Item(ItemId(UUID(int=23)), "epic", None, "Rooms", "Managing rooms.")
    moved = replace(STORY, parent_id=other_epic.id)

    changes = compare_items((EPIC, other_epic, STORY), (EPIC, other_epic, moved))

    assert [(c.kind, c.changed_fields) for c in changes] == [("modify_item", ("parent_id",))]


def test_a_rejected_suggestion_counts_as_absent() -> None:
    rejected = replace(STORY, criteria=(SOURCED, replace(SUGGESTED, suggestion="rejected")))

    (change,) = compare_items((EPIC, STORY), (EPIC, rejected))

    assert [(c.kind, c.criterion_id) for c in change.criteria] == [("removed", SUGGESTED.id)]


def test_provenance_alone_is_not_a_change() -> None:
    reviewed = replace(
        STORY,
        human_edited=True,
        edited_by=EDITOR,
        edited_at=NOW,
        criteria=(replace(SOURCED, edited_by=EDITOR), SUGGESTED),
    )

    assert compare_items((EPIC, STORY), (EPIC, reviewed)) == ()


def test_a_cursor_round_trips() -> None:
    cursor = ListCursor(NOW, BacklogVersionId(UUID(int=40)))

    assert decode_cursor(encode_cursor(cursor)) == cursor


@pytest.mark.parametrize(
    "value",
    [
        "not base64!",
        base64.urlsafe_b64encode(b"not a cursor").decode(),
        base64.urlsafe_b64encode(f"2026-10-14T09:00:00|{UUID(int=1)}".encode()).decode(),
    ],
)
def test_a_cursor_this_list_did_not_return_is_invalid(value: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(value)


def _listing(n: int, state: VersionState = VersionState.APPROVED) -> VersionListing:
    return VersionListing(
        id=BacklogVersionId(UUID(int=100 + n)),
        state=state,
        revision=1,
        content_hash=f"{n:064d}",
        base_version_id=None,
        run_id=None,
        created_by=EDITOR,
        created_at=NOW + timedelta(minutes=n),
    )


class Listings:
    def __init__(self, *listings: VersionListing) -> None:
        self.listings = sorted(listings, key=lambda v: (v.created_at, v.id), reverse=True)

    def newest_first(
        self, project_id: ProjectId, *, after: ListCursor | None, limit: int
    ) -> list[VersionListing]:
        rows = [
            v
            for v in self.listings
            if after is None or (v.created_at, v.id) < (after.created_at, after.id)
        ]
        return rows[:limit]


def _reader(*decisions: VersionDecision) -> DecisionReader:
    def read(ids: Collection[BacklogVersionId]) -> Mapping[BacklogVersionId, VersionDecision]:
        return {d.version_id: d for d in decisions if d.version_id in ids}

    return read


def _access(*roles: Role) -> ProjectAccess:
    return ProjectAccess(Actor(EDITOR, "Eden"), PROJECT, frozenset(roles))


def test_versions_are_paged_newest_first_with_their_decisions() -> None:
    store = Listings(_listing(1), _listing(2), _listing(3, VersionState.DRAFT))
    approval = VersionDecision(_listing(2).id, "approved", EDITOR, NOW, 2)

    first = list_versions(store, _reader(approval), _access(Role.VIEWER), limit=2, cursor=None)
    second = list_versions(
        store, _reader(approval), _access(Role.VIEWER), limit=2, cursor=first.next_cursor
    )

    assert [v.version.id for v in first.versions] == [_listing(3).id, _listing(2).id]
    assert [v.decision for v in first.versions] == [None, approval]
    assert [v.version.id for v in second.versions] == [_listing(1).id]
    assert second.next_cursor is None


def test_an_empty_project_has_an_empty_page() -> None:
    page = list_versions(Listings(), _reader(), _access(Role.VIEWER), limit=20, cursor=None)

    assert (page.versions, page.next_cursor) == ((), None)


def test_a_non_member_cannot_list_versions() -> None:
    with pytest.raises(NotFoundError):
        list_versions(Listings(_listing(1)), _reader(), _access(), limit=20, cursor=None)
