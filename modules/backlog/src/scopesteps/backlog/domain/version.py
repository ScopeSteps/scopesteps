"""A backlog version: epics and stories, the decisions raised about them and what was left out.

Blockers are derived from the content every time they are read, so they cannot outlive the
decision or proposal that caused them.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, DecisionId, ItemId
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId

# Ceilings from the POC scope contract, not quotas: a smaller backlog is always valid.
MAX_EPICS = 2
MAX_STORIES = 8
MAX_TITLE_CHARS = 200

ItemKind = Literal["epic", "story"]
ClaimOrigin = Literal["source", "human", "proposed"]
DecisionKind = Literal["conflict", "missing_decision"]
DecisionStatus = Literal["open", "skipped", "answered"]
ScopeNoteKind = Literal["excluded", "suggested"]
BlockerCode = Literal["unresolved_conflict", "open_decision", "proposed_criterion"]


class VersionState(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Evidence:
    """An exact stored passage. `quote` is None when the whole paragraph is cited."""

    source_version_id: UUID
    block_id: UUID
    quote: str | None = None
    relationship: Literal["supporting", "conflicting"] = "supporting"


@dataclass(frozen=True)
class Criterion:
    id: CriterionId
    text: str
    origin: ClaimOrigin
    evidence: tuple[Evidence, ...] = ()
    confirmed_by: tuple[DecisionId, ...] = ()
    """The answered decisions that make this criterion human-confirmed."""


@dataclass(frozen=True)
class Item:
    """An epic or story. `id` is stable across versions and never reused for other work."""

    id: ItemId
    kind: ItemKind
    parent_id: ItemId | None
    title: str
    description: str
    criteria: tuple[Criterion, ...] = ()
    assumptions: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    human_edited: bool = False


@dataclass(frozen=True)
class Decision:
    """Something only a reviewer can settle. It stays unresolved until a reviewer answers it:
    skipping it, or answering something related, never settles it."""

    id: DecisionId
    kind: DecisionKind
    status: DecisionStatus
    subject: str
    question: str
    why_it_matters: str
    evidence: tuple[Evidence, ...] = ()
    affected_item_ids: tuple[ItemId, ...] = ()
    question_id: UUID | None = None
    """The clarification question a reviewer answered or skipped, if it was put to one."""
    answer: str | None = None
    decided_by: UserId | None = None
    decided_at: datetime | None = None

    @property
    def is_resolved(self) -> bool:
        return self.status == "answered"


@dataclass(frozen=True)
class ScopeNote:
    """Work the sources rule out or only suggest. Recorded so its absence is a visible decision."""

    kind: ScopeNoteKind
    summary: str
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class Blocker:
    """A reason scope cannot be approved yet. `item_id` is None when no item is affected."""

    code: BlockerCode
    message: str
    item_id: ItemId | None = None
    decision_id: DecisionId | None = None
    criterion_id: CriterionId | None = None


@dataclass(frozen=True)
class BacklogVersion:
    id: BacklogVersionId
    project_id: ProjectId
    base_version_id: BacklogVersionId | None
    revision: int
    state: VersionState
    content_hash: str
    run_id: UUID | None
    """The agent run that proposed this version, if one did."""
    source_version_ids: tuple[UUID, ...]
    items: tuple[Item, ...]
    decisions: tuple[Decision, ...]
    out_of_scope: tuple[ScopeNote, ...]
    created_by: UserId
    created_at: datetime

    def blockers(self) -> tuple[Blocker, ...]:
        return find_blockers(self.items, self.decisions)


def find_blockers(items: tuple[Item, ...], decisions: tuple[Decision, ...]) -> tuple[Blocker, ...]:
    """Unresolved decisions block the items they affect; AI-proposed criteria block their item
    until a reviewer accepts, edits or removes them."""
    blockers: list[Blocker] = []
    for decision in decisions:
        if decision.is_resolved:
            continue
        code: BlockerCode = (
            "unresolved_conflict" if decision.kind == "conflict" else "open_decision"
        )
        reason = {
            ("conflict", "open"): "Sources conflict",
            ("conflict", "skipped"): "Sources conflict and the question was skipped",
            ("missing_decision", "skipped"): "The reviewer skipped this decision",
        }.get((decision.kind, decision.status), "Decision needed")
        message = f"{reason}: {decision.subject}"
        blockers += [
            Blocker(code, message, item_id, decision.id)
            for item_id in decision.affected_item_ids or (None,)
        ]
    for item in items:
        blockers += [
            Blocker(
                "proposed_criterion",
                "An AI-proposed criterion has not been reviewed",
                item.id,
                criterion_id=criterion.id,
            )
            for criterion in item.criteria
            if criterion.origin == "proposed"
        ]
    return tuple(blockers)


def content_hash(
    items: tuple[Item, ...], decisions: tuple[Decision, ...], out_of_scope: tuple[ScopeNote, ...]
) -> str:
    """Identifies the exact content an approval refers to."""
    content = {
        "items": [asdict(item) for item in items],
        "decisions": [asdict(decision) for decision in decisions],
        "out_of_scope": [asdict(note) for note in out_of_scope],
    }
    canonical = json.dumps(content, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
