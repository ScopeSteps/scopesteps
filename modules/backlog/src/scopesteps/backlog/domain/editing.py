"""A person's edit to one item of a draft version.

Ids are stable: an edited criterion keeps its id, evidence and origin, and a criterion a person
adds gets a new id with the `person` origin. Who changed what is recorded on the item and on each
criterion whose text a person wrote.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from scopesteps.backlog.domain.ids import CriterionId
from scopesteps.backlog.domain.version import MAX_TITLE_CHARS, Criterion, Item, SuggestionStatus
from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import ConflictError, InvalidInputError


class VersionChangedError(ConflictError):
    """The version changed after the caller read it; nothing from this request was saved."""

    code = "VERSION_CHANGED"


class VersionNotDraftError(ConflictError):
    """Only a draft can be edited, approved or rejected; approved versions never change."""

    code = "VERSION_NOT_DRAFT"


class InvalidItemEditError(InvalidInputError):
    code = "ITEM_EDIT_INVALID"

    def __init__(self, problems: list[str]) -> None:
        super().__init__(
            "The edit was not saved: " + "; ".join(problems), details={"problems": problems}
        )


@dataclass(frozen=True)
class CriterionEdit:
    id: CriterionId | None
    """None adds a criterion written by the editor."""
    text: str
    suggestion: SuggestionStatus | None = None
    """Accept, reject or reopen an agent suggestion; None leaves its status as it is."""


@dataclass(frozen=True)
class ItemEdit:
    """Fields left as None are unchanged. `criteria` is the item's whole new list, in order:
    a criterion left out is removed."""

    title: str | None = None
    description: str | None = None
    criteria: tuple[CriterionEdit, ...] | None = None


@dataclass(frozen=True)
class EditSummary:
    """What an edit changed, counted for the activity log."""

    title: bool = False
    description: bool = False
    added: int = 0
    edited: int = 0
    removed: int = 0
    accepted: int = 0
    rejected: int = 0
    reopened: int = 0

    @property
    def changes_content(self) -> bool:
        return self.title or self.description or bool(self.added + self.edited + self.removed)

    @property
    def changes_anything(self) -> bool:
        return self.changes_content or bool(self.accepted + self.rejected + self.reopened)

    def describe(self) -> str:
        parts = [
            *(["changed the title"] if self.title else []),
            *(["changed the description"] if self.description else []),
            *_counted(self.added, "added"),
            *_counted(self.edited, "edited"),
            *_counted(self.removed, "removed"),
            *_counted(self.accepted, "accepted", "suggestion", "suggestions"),
            *_counted(self.rejected, "rejected", "suggestion", "suggestions"),
            *_counted(self.reopened, "reopened", "suggestion", "suggestions"),
        ]
        return ", ".join(parts)


def _counted(number: int, verb: str, one: str = "criterion", many: str = "criteria") -> list[str]:
    return [f"{verb} {number} {one if number == 1 else many}"] if number else []


def apply_edit(
    item: Item, edit: ItemEdit, *, editor: UserId, now: datetime, new_id: Callable[[], UUID]
) -> tuple[Item, EditSummary]:
    """The item after `edit`, and what changed. An edit that changes nothing returns the item
    as it was. Raises InvalidItemEditError, changing nothing, if the edit breaks a rule."""
    problems: list[str] = []
    title = item.title if edit.title is None else edit.title.strip()
    if not title or len(title) > MAX_TITLE_CHARS:
        problems.append(f"a title is 1 to {MAX_TITLE_CHARS} characters")
    description = item.description if edit.description is None else edit.description.strip()
    criteria = item.criteria
    counts = EditSummary()
    if edit.criteria is not None:
        criteria, counts, criteria_problems = _edit_criteria(item, edit.criteria, editor, new_id)
        problems += criteria_problems
    if problems:
        raise InvalidItemEditError(problems)

    summary = replace(
        counts, title=title != item.title, description=description != item.description
    )
    if not summary.changes_anything:
        return item, summary
    edited = replace(
        item,
        title=title,
        description=description,
        criteria=criteria,
        human_edited=item.human_edited or summary.changes_content,
        edited_by=editor,
        edited_at=now,
    )
    return edited, summary


def _edit_criteria(
    item: Item,
    edits: tuple[CriterionEdit, ...],
    editor: UserId,
    new_id: Callable[[], UUID],
) -> tuple[tuple[Criterion, ...], EditSummary, list[str]]:
    existing = {criterion.id: criterion for criterion in item.criteria}
    problems: list[str] = []
    repeated = [str(i) for i, n in Counter(e.id for e in edits if e.id).items() if n > 1]
    problems += [f"criterion {criterion_id} is listed more than once" for criterion_id in repeated]
    criteria: list[Criterion] = []
    added = edited = accepted = rejected = reopened = 0
    for position, criterion_edit in enumerate(edits, start=1):
        text = criterion_edit.text.strip()
        if not text:
            problems.append(f"criterion {position} has no text")
        if criterion_edit.id is None:
            if criterion_edit.suggestion is not None:
                problems.append(f"criterion {position} is new, so it is not an agent suggestion")
            criteria.append(
                Criterion(id=CriterionId(new_id()), text=text, origin="person", edited_by=editor)
            )
            added += 1
            continue
        old = existing.get(criterion_edit.id)
        if old is None:
            problems.append(f"criterion {criterion_edit.id} is not on this item")
            continue
        if criterion_edit.suggestion is not None and old.suggestion is None:
            problems.append(f"criterion {old.id} is not an agent suggestion")
            continue
        text_changed = text != old.text
        suggestion = criterion_edit.suggestion or old.suggestion
        # Rewriting a suggestion keeps it, so it counts as accepting it unless the edit says
        # otherwise.
        if text_changed and old.suggestion is not None and criterion_edit.suggestion is None:
            suggestion = "accepted"
        if suggestion != old.suggestion:
            if suggestion == "accepted":
                accepted += 1
            elif suggestion == "rejected":
                rejected += 1
            else:
                reopened += 1
        edited += text_changed
        criteria.append(
            replace(
                old,
                text=text,
                suggestion=suggestion,
                edited_by=editor if text_changed else old.edited_by,
            )
        )
    kept = {criterion_edit.id for criterion_edit in edits}
    removed = sum(1 for criterion_id in existing if criterion_id not in kept)
    summary = EditSummary(
        added=added,
        edited=edited,
        removed=removed,
        accepted=accepted,
        rejected=rejected,
        reopened=reopened,
    )
    return tuple(criteria), summary, problems
