"""A change to an approved baseline, proposed by a change run, and the candidate it becomes.

The proposal names existing work by its stable ids, and only what it adds, edits or removes. The
candidate is built from the baseline: every item the proposal does not touch is copied with its
id, content and provenance, so a deterministic comparison with the baseline shows exactly the
proposed operations. The baseline itself is only read (ADR 0011).
"""

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

from scopesteps.backlog.domain.candidate import (
    MAX_REPORTED_PROBLEMS,
    ProposedCriterion,
    criterion_origin,
)
from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, DecisionId, ItemId
from scopesteps.backlog.domain.review import structure_problems
from scopesteps.backlog.domain.version import (
    MAX_TITLE_CHARS,
    BacklogVersion,
    Criterion,
    Decision,
    DecisionKind,
    DecisionStatus,
    Evidence,
    Item,
    ItemKind,
    VersionState,
    content_hash,
)
from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import InvalidInputError
from scopesteps.projects.client import ProjectId

ItemRef = ItemId | str
"""An existing item, by its stable id, or a new item of the same proposal, by its ref."""


class ChangeRejectedError(InvalidInputError):
    code = "CHANGE_REJECTED"

    def __init__(self, problems: list[str]) -> None:
        super().__init__(
            "The proposed change failed validation and was not saved",
            details={"problems": problems[:MAX_REPORTED_PROBLEMS], "count": len(problems)},
        )
        self.problems = problems


@dataclass(frozen=True)
class CriterionEdit:
    """New content for an existing criterion, which keeps its id."""

    criterion_id: CriterionId
    criterion: ProposedCriterion


@dataclass(frozen=True)
class ItemEdit:
    """What changes on one existing item. None leaves a field as it is."""

    item_id: ItemId
    title: str | None = None
    description: str | None = None
    added_criteria: tuple[ProposedCriterion, ...] = ()
    changed_criteria: tuple[CriterionEdit, ...] = ()
    removed_criteria: tuple[CriterionId, ...] = ()


@dataclass(frozen=True)
class NewItem:
    ref: str
    """Unique within the proposal; decisions and stories refer to the new item by it."""
    kind: ItemKind
    parent: ItemRef | None
    title: str
    description: str
    criteria: tuple[ProposedCriterion, ...] = ()


@dataclass(frozen=True)
class ChangeDecision:
    """A decision the change raises or a reviewer settled during the change run."""

    key: str
    kind: DecisionKind
    status: DecisionStatus
    subject: str
    question: str
    why_it_matters: str
    evidence: tuple[Evidence, ...] = ()
    affects: tuple[ItemRef, ...] = ()
    question_id: UUID | None = None
    answer: str | None = None
    decided_by: UserId | None = None
    decided_at: datetime | None = None


@dataclass(frozen=True)
class ChangeProposal:
    project_id: ProjectId
    run_id: UUID
    created_by: UserId
    base_version_id: BacklogVersionId
    base_content_hash: str
    """The baseline exactly as the change run read it; any other content is refused."""
    source_version_ids: tuple[UUID, ...]
    """The versions the change run pinned: the baseline's sources and the request's text."""
    added: tuple[NewItem, ...] = ()
    edited: tuple[ItemEdit, ...] = ()
    removed: tuple[ItemId, ...] = ()
    decisions: tuple[ChangeDecision, ...] = ()
    reversed_exclusions: tuple[int, ...] = ()
    """Positions in the baseline's `out_of_scope` of the exclusions the change takes back. Each
    must be named by an open scope_reversal decision, so an approver decides it."""

    def evidence(self) -> list[Evidence]:
        criteria = [
            *(c for item in self.added for c in item.criteria),
            *(c for edit in self.edited for c in edit.added_criteria),
            *(e.criterion for edit in self.edited for e in edit.changed_criteria),
        ]
        return [
            *(e for criterion in criteria for e in criterion.evidence),
            *(e for decision in self.decisions for e in decision.evidence),
        ]

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.edited or self.removed or self.reversed_exclusions)


def change_problems(base: BacklogVersion, proposal: ChangeProposal) -> list[str]:
    """Why the proposal cannot be applied to `base`; empty when `build_change_candidate` will
    accept it. Evidence is checked by the caller against what is stored."""
    problems: list[str] = []
    if base.id != proposal.base_version_id or base.project_id != proposal.project_id:
        return ["the change is not based on a version of this project"]
    if base.state is not VersionState.APPROVED:
        return [f"version {base.id} is not an approved baseline"]
    if base.content_hash != proposal.base_content_hash:
        return [f"version {base.id} does not have the content hash the change was made from"]
    if proposal.is_empty:
        problems.append("the change adds, changes and removes nothing")

    existing = {item.id: item for item in base.items}
    touched = Counter([*(e.item_id for e in proposal.edited), *proposal.removed])
    problems += [f"item {i} is changed {n} times" for i, n in touched.items() if n > 1]
    problems += [f"item {i} is not in the baseline" for i in touched if i not in existing]
    for edit in proposal.edited:
        item = existing.get(edit.item_id)
        if item is None:
            continue
        own = {criterion.id for criterion in item.criteria}
        named = [*(c.criterion_id for c in edit.changed_criteria), *edit.removed_criteria]
        problems += [
            f"criterion {c} is not on item {item.id}" for c in dict.fromkeys(named) if c not in own
        ]
        problems += [
            f"criterion {c} is changed more than once on item {item.id}"
            for c, n in Counter(named).items()
            if n > 1
        ]
        if edit.title is not None and not _valid_title(edit.title):
            problems.append(f"item {item.id} needs a title of 1 to {MAX_TITLE_CHARS} characters")
    refs = Counter(item.ref for item in proposal.added)
    problems += [f"new item ref {r} is used {n} times" for r, n in refs.items() if n > 1]
    for item in proposal.added:
        if not _valid_title(item.title):
            problems.append(f"{item.ref} needs a title of 1 to {MAX_TITLE_CHARS} characters")
        if any(not criterion.text.strip() for criterion in item.criteria):
            problems.append(f"{item.ref} has an empty acceptance criterion")
    for edit in proposal.edited:
        criteria = [*edit.added_criteria, *(c.criterion for c in edit.changed_criteria)]
        if any(not criterion.text.strip() for criterion in criteria):
            problems.append(f"item {edit.item_id} has an empty acceptance criterion")

    keys = Counter(decision.key for decision in proposal.decisions)
    problems += [f"decision {k} is given {n} times" for k, n in keys.items() if n > 1]
    answered = {d.key for d in proposal.decisions if d.status == "answered"}
    for decision in proposal.decisions:
        if (decision.status == "answered") != bool(decision.answer and decision.answer.strip()):
            problems.append(f"decision {decision.key} must have an answer exactly when answered")
        if decision.status != "open" and (
            decision.decided_by is None or decision.decided_at is None
        ):
            problems.append(f"decision {decision.key} does not record who decided it and when")
        if decision.kind == "scope_reversal" and decision.status != "open":
            problems.append(f"decision {decision.key} is a scope decision only an approver makes")
    confirming = {
        key
        for criterion in _proposed_criteria(proposal)
        for key in criterion.confirmed_by
        if key not in answered
    }
    problems += [f"criteria cite decision {k}, which no reviewer answered" for k in confirming]
    for position in proposal.reversed_exclusions:
        if not 0 <= position < len(base.out_of_scope):
            problems.append(f"the baseline has no out-of-scope note {position}")
        elif base.out_of_scope[position].kind != "excluded":
            problems.append(f"out-of-scope note {position} is a suggestion, not an exclusion")
    if proposal.reversed_exclusions and not any(
        d.kind == "scope_reversal" and d.status == "open" for d in proposal.decisions
    ):
        problems.append("an exclusion is reversed without a scope decision for an approver")
    if problems:
        return problems

    try:
        # A trial build with throwaway ids, so the result's structure is checked as a whole.
        candidate = _apply(base, proposal, new_id=uuid4, now=base.created_at).version
    except _UnknownReferenceError as error:
        return [str(error)]
    return structure_problems(candidate)


@dataclass(frozen=True)
class BuiltChange:
    version: BacklogVersion
    item_ids: dict[str, ItemId]
    """The id each new item's ref received."""
    decision_ids: dict[str, DecisionId]
    """The id each decision's key received."""


def build_change_candidate(
    base: BacklogVersion,
    proposal: ChangeProposal,
    *,
    new_id: Callable[[], UUID],
    now: datetime,
) -> BuiltChange:
    """The baseline with the proposal applied, as a new version in review. Raises
    ChangeRejectedError if the proposal does not hold up against `base`."""
    problems = change_problems(base, proposal)
    if problems:
        raise ChangeRejectedError(problems)
    return _apply(base, proposal, new_id=new_id, now=now)


class _UnknownReferenceError(Exception):
    pass


def _apply(
    base: BacklogVersion,
    proposal: ChangeProposal,
    *,
    new_id: Callable[[], UUID],
    now: datetime,
) -> BuiltChange:
    item_ids = {item.ref: ItemId(new_id()) for item in proposal.added}
    decision_ids = {decision.key: DecisionId(new_id()) for decision in proposal.decisions}
    removed = set(proposal.removed)
    edits = {edit.item_id: edit for edit in proposal.edited}

    def resolve(ref: ItemRef) -> ItemId:
        if isinstance(ref, str):
            if ref not in item_ids:
                raise _UnknownReferenceError(f"no new item has the ref {ref}")
            return item_ids[ref]
        return ref

    def criterion(proposed: ProposedCriterion, criterion_id: CriterionId) -> Criterion:
        origin = criterion_origin(proposed)
        return Criterion(
            id=criterion_id,
            text=proposed.text.strip(),
            origin=origin,
            evidence=proposed.evidence,
            confirmed_by=tuple(decision_ids[key] for key in proposed.confirmed_by),
            suggestion="pending" if origin == "proposed" else None,
        )

    items: list[Item] = []
    for item in base.items:
        if item.id in removed:
            continue
        edit = edits.get(item.id)
        items.append(item if edit is None else _edited(item, edit, criterion, new_id))
    for added in proposal.added:
        items.append(
            Item(
                id=item_ids[added.ref],
                kind=added.kind,
                parent_id=None if added.parent is None else resolve(added.parent),
                title=added.title.strip(),
                description=added.description.strip(),
                criteria=tuple(
                    criterion(proposed, CriterionId(new_id())) for proposed in added.criteria
                ),
            )
        )
    kept = {item.id for item in items}
    decisions = [
        replace(
            decision,
            affected_item_ids=tuple(i for i in decision.affected_item_ids if i in kept),
        )
        for decision in base.decisions
    ]
    decisions += [
        Decision(
            id=decision_ids[decision.key],
            kind=decision.kind,
            status=decision.status,
            subject=decision.subject,
            question=decision.question,
            why_it_matters=decision.why_it_matters,
            evidence=decision.evidence,
            affected_item_ids=tuple(dict.fromkeys(resolve(ref) for ref in decision.affects)),
            question_id=decision.question_id,
            answer=decision.answer,
            decided_by=decision.decided_by,
            decided_at=decision.decided_at,
        )
        for decision in proposal.decisions
    ]
    reversed_positions = set(proposal.reversed_exclusions)
    out_of_scope = tuple(
        note
        for position, note in enumerate(base.out_of_scope)
        if position not in reversed_positions
    )
    version = BacklogVersion(
        id=BacklogVersionId(new_id()),
        project_id=base.project_id,
        base_version_id=base.id,
        revision=1,
        state=VersionState.IN_REVIEW,
        content_hash=content_hash(tuple(items), tuple(decisions), out_of_scope),
        run_id=proposal.run_id,
        source_version_ids=proposal.source_version_ids,
        items=tuple(items),
        decisions=tuple(decisions),
        out_of_scope=out_of_scope,
        created_by=proposal.created_by,
        created_at=now,
    )
    return BuiltChange(version, item_ids, decision_ids)


def _edited(
    item: Item,
    edit: ItemEdit,
    criterion: Callable[[ProposedCriterion, CriterionId], Criterion],
    new_id: Callable[[], UUID],
) -> Item:
    """The item with the edit applied. It keeps its id and its record of human edits: the change
    is the agent's proposal, which a person reviews as a whole."""
    changed = {c.criterion_id: c.criterion for c in edit.changed_criteria}
    removed = set(edit.removed_criteria)
    criteria = [
        criterion(changed[c.id], c.id) if c.id in changed else c
        for c in item.criteria
        if c.id not in removed
    ]
    criteria += [criterion(proposed, CriterionId(new_id())) for proposed in edit.added_criteria]
    return replace(
        item,
        title=item.title if edit.title is None else edit.title.strip(),
        description=item.description if edit.description is None else edit.description.strip(),
        criteria=tuple(criteria),
    )


def _proposed_criteria(proposal: ChangeProposal) -> Iterable[ProposedCriterion]:
    yield from (c for item in proposal.added for c in item.criteria)
    yield from (c for edit in proposal.edited for c in edit.added_criteria)
    yield from (e.criterion for edit in proposal.edited for e in edit.changed_criteria)


def _valid_title(title: str) -> bool:
    return bool(title.strip()) and len(title) <= MAX_TITLE_CHARS
