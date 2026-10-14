"""A project's versions over time, and what changed between any two of them.

Comparison works on stable ids: an item or criterion that keeps its id is the same work, however
much its text changed, and one with a new id is new work.
"""

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, ItemId
from scopesteps.backlog.domain.version import Criterion, Item, VersionState, approved_content
from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import InvalidInputError

ItemChangeKind = Literal["add_item", "modify_item", "remove_item"]
CriterionChangeKind = Literal["added", "removed", "modified"]
ItemField = Literal["kind", "parent_id", "title", "description", "assumptions", "open_questions"]

ITEM_FIELDS: tuple[ItemField, ...] = (
    "kind",
    "parent_id",
    "title",
    "description",
    "assumptions",
    "open_questions",
)


class InvalidCursorError(InvalidInputError):
    code = "INVALID_CURSOR"


@dataclass(frozen=True)
class VersionListing:
    """A version without its content: enough to list it, newest first."""

    id: BacklogVersionId
    state: VersionState
    revision: int
    content_hash: str
    base_version_id: BacklogVersionId | None
    run_id: UUID | None
    created_by: UserId
    created_at: datetime


@dataclass(frozen=True)
class ListCursor:
    """The last version of a page; the next page starts after it."""

    created_at: datetime
    id: BacklogVersionId


def encode_cursor(cursor: ListCursor) -> str:
    raw = f"{cursor.created_at.isoformat()}|{cursor.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(value: str) -> ListCursor:
    try:
        created_at, _, version_id = base64.urlsafe_b64decode(value).decode().partition("|")
        cursor = ListCursor(datetime.fromisoformat(created_at), BacklogVersionId(UUID(version_id)))
    except (ValueError, binascii.Error) as error:
        raise InvalidCursorError("The cursor is not one this list returned") from error
    if cursor.created_at.tzinfo is None:
        raise InvalidCursorError("The cursor is not one this list returned")
    return cursor


@dataclass(frozen=True)
class CriterionChange:
    kind: CriterionChangeKind
    criterion_id: CriterionId
    before: Criterion | None
    after: Criterion | None


@dataclass(frozen=True)
class ItemChange:
    """One item's change, shaped like a change set's operation. `before` is None for an added
    item and `after` for a removed one."""

    kind: ItemChangeKind
    item_id: ItemId
    before: Item | None
    after: Item | None
    changed_fields: tuple[ItemField, ...] = ()
    criteria: tuple[CriterionChange, ...] = ()


def _criterion_content(criterion: Criterion) -> tuple[object, ...]:
    # Who last wrote the text and the review state of a suggestion are provenance, not content.
    return (criterion.text, criterion.origin, criterion.evidence, criterion.confirmed_by)


def _criterion_changes(before: Item, after: Item) -> tuple[CriterionChange, ...]:
    old = {criterion.id: criterion for criterion in before.criteria}
    new = {criterion.id: criterion for criterion in after.criteria}
    changes: list[CriterionChange] = []
    for criterion in after.criteria:
        previous = old.get(criterion.id)
        if previous is None:
            changes.append(CriterionChange("added", criterion.id, None, criterion))
        elif _criterion_content(previous) != _criterion_content(criterion):
            changes.append(CriterionChange("modified", criterion.id, previous, criterion))
    changes += [
        CriterionChange("removed", criterion.id, criterion, None)
        for criterion in before.criteria
        if criterion.id not in new
    ]
    return tuple(changes)


def compare_items(base: tuple[Item, ...], candidate: tuple[Item, ...]) -> tuple[ItemChange, ...]:
    """What changes from `base` to `candidate`, compared as approval freezes each of them (so a
    rejected suggestion counts as absent). Items in the candidate's order, then removed ones."""
    old = {item.id: item for item in approved_content(base)}
    new_items = approved_content(candidate)
    new_ids = {item.id for item in new_items}
    changes: list[ItemChange] = []
    for item in new_items:
        previous = old.get(item.id)
        if previous is None:
            changes.append(ItemChange("add_item", item.id, None, item))
            continue
        fields: tuple[ItemField, ...] = tuple(
            f for f in ITEM_FIELDS if getattr(previous, f) != getattr(item, f)
        )
        criteria = _criterion_changes(previous, item)
        if fields or criteria:
            changes.append(ItemChange("modify_item", item.id, previous, item, fields, criteria))
    changes += [
        ItemChange("remove_item", item.id, item, None)
        for item in old.values()
        if item.id not in new_ids
    ]
    return tuple(changes)
