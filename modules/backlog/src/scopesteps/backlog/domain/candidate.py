"""A candidate proposed by an agent run. It is untrusted until it passes the checks here and the
citation checks in the application layer; only then does it become a draft version with ids."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, DecisionId, ItemId
from scopesteps.backlog.domain.version import (
    MAX_EPICS,
    MAX_STORIES,
    MAX_TITLE_CHARS,
    BacklogVersion,
    ClaimOrigin,
    Criterion,
    Decision,
    DecisionKind,
    DecisionStatus,
    Evidence,
    Item,
    ItemKind,
    ScopeNote,
    SetAsideNote,
    VersionState,
    content_hash,
)
from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import InvalidInputError
from scopesteps.projects.client import ProjectId

MAX_REPORTED_PROBLEMS = 10


class CandidateRejectedError(InvalidInputError):
    code = "CANDIDATE_REJECTED"

    def __init__(self, problems: list[str]) -> None:
        super().__init__(
            "The proposed backlog failed validation and was not saved",
            details={"problems": problems[:MAX_REPORTED_PROBLEMS], "count": len(problems)},
        )
        self.problems = problems


@dataclass(frozen=True)
class ProposedCriterion:
    text: str
    proposed: bool
    """True for a detail the agent added itself. It stays proposed whatever it cites."""
    evidence: tuple[Evidence, ...] = ()
    confirmed_by: tuple[str, ...] = ()
    """Keys of the answered decisions that confirm it."""


@dataclass(frozen=True)
class ProposedItem:
    ref: str
    """Unique within the proposal; parents and decisions refer to items by it."""
    kind: ItemKind
    parent_ref: str | None
    title: str
    description: str
    criteria: tuple[ProposedCriterion, ...] = ()
    assumptions: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProposedDecision:
    key: str
    kind: DecisionKind
    status: DecisionStatus
    subject: str
    question: str
    why_it_matters: str
    evidence: tuple[Evidence, ...] = ()
    affects: tuple[str, ...] = ()
    question_id: UUID | None = None
    answer: str | None = None
    decided_by: UserId | None = None
    decided_at: datetime | None = None


@dataclass(frozen=True)
class CandidateProposal:
    project_id: ProjectId
    run_id: UUID
    created_by: UserId
    source_version_ids: tuple[UUID, ...]
    """The versions the run pinned. Evidence may cite nothing else."""
    items: tuple[ProposedItem, ...]
    decisions: tuple[ProposedDecision, ...] = ()
    out_of_scope: tuple[ScopeNote, ...] = ()
    set_aside: tuple[SetAsideNote, ...] = ()

    def evidence(self) -> list[Evidence]:
        return [
            *(e for item in self.items for criterion in item.criteria for e in criterion.evidence),
            *(e for decision in self.decisions for e in decision.evidence),
            *(e for note in self.out_of_scope for e in note.evidence),
            *(e for note in self.set_aside for e in note.evidence),
        ]


def structural_problems(proposal: CandidateProposal) -> list[str]:
    """Problems with ids, hierarchy, limits and decisions; empty when the proposal is sound."""
    problems: list[str] = []
    refs = Counter(item.ref for item in proposal.items)
    problems += [
        f"item ref {ref} is used {count} times" for ref, count in refs.items() if count > 1
    ]
    epics = {item.ref for item in proposal.items if item.kind == "epic"}
    stories = len(proposal.items) - len(epics)
    if len(epics) > MAX_EPICS:
        problems.append(f"{len(epics)} epics exceed the limit of {MAX_EPICS}")
    if stories > MAX_STORIES:
        problems.append(f"{stories} stories exceed the limit of {MAX_STORIES}")

    for item in proposal.items:
        if not item.title.strip() or len(item.title) > MAX_TITLE_CHARS:
            problems.append(f"{item.ref} needs a title of at most {MAX_TITLE_CHARS} characters")
        if item.kind == "epic" and item.parent_ref is not None:
            problems.append(f"epic {item.ref} cannot have a parent")
        if item.kind == "story" and item.parent_ref not in epics:
            problems.append(f"story {item.ref} has no epic {item.parent_ref!r} to belong to")
        if any(not criterion.text.strip() for criterion in item.criteria):
            problems.append(f"{item.ref} has an empty acceptance criterion")

    keys = Counter(decision.key for decision in proposal.decisions)
    problems += [
        f"decision {key} is given {count} times" for key, count in keys.items() if count > 1
    ]
    answered = {d.key for d in proposal.decisions if d.status == "answered"}
    for decision in proposal.decisions:
        if (decision.status == "answered") != bool(decision.answer and decision.answer.strip()):
            problems.append(f"decision {decision.key} must have an answer exactly when answered")
        if decision.status != "open" and (
            decision.decided_by is None or decision.decided_at is None
        ):
            problems.append(f"decision {decision.key} does not record who decided it and when")
        unknown = sorted(set(decision.affects) - refs.keys())
        if unknown:
            problems.append(f"decision {decision.key} affects unknown items {', '.join(unknown)}")
    for item in proposal.items:
        unconfirmed = sorted(
            {key for criterion in item.criteria for key in criterion.confirmed_by} - answered
        )
        if unconfirmed:
            problems.append(
                f"{item.ref} is confirmed by {', '.join(unconfirmed)}, which no reviewer answered"
            )
    return problems


def criterion_origin(criterion: ProposedCriterion) -> ClaimOrigin:
    """A claim is only as strong as its support: without a passage or a reviewer's answer it is
    proposed, whatever the proposal called it."""
    if criterion.proposed or not (criterion.evidence or criterion.confirmed_by):
        return "proposed"
    return "human" if criterion.confirmed_by else "source"


def build_candidate(
    proposal: CandidateProposal, *, new_id: Callable[[], UUID], now: datetime
) -> BacklogVersion:
    """Give a sound proposal its stable ids. Raises CandidateRejectedError if it is not sound."""
    problems = structural_problems(proposal)
    if problems:
        raise CandidateRejectedError(problems)
    item_ids = {item.ref: ItemId(new_id()) for item in proposal.items}
    decision_ids = {decision.key: DecisionId(new_id()) for decision in proposal.decisions}
    items = tuple(
        Item(
            id=item_ids[item.ref],
            kind=item.kind,
            parent_id=None if item.parent_ref is None else item_ids[item.parent_ref],
            title=item.title.strip(),
            description=item.description.strip(),
            criteria=tuple(
                Criterion(
                    id=CriterionId(new_id()),
                    text=criterion.text.strip(),
                    origin=criterion_origin(criterion),
                    evidence=criterion.evidence,
                    confirmed_by=tuple(decision_ids[key] for key in criterion.confirmed_by),
                    suggestion="pending" if criterion_origin(criterion) == "proposed" else None,
                )
                for criterion in item.criteria
            ),
            assumptions=item.assumptions,
            open_questions=item.open_questions,
        )
        for item in proposal.items
    )
    decisions = tuple(
        Decision(
            id=decision_ids[decision.key],
            kind=decision.kind,
            status=decision.status,
            subject=decision.subject,
            question=decision.question,
            why_it_matters=decision.why_it_matters,
            evidence=decision.evidence,
            affected_item_ids=tuple(item_ids[ref] for ref in dict.fromkeys(decision.affects)),
            question_id=decision.question_id,
            answer=decision.answer,
            decided_by=decision.decided_by,
            decided_at=decision.decided_at,
        )
        for decision in proposal.decisions
    )
    return BacklogVersion(
        id=BacklogVersionId(new_id()),
        project_id=proposal.project_id,
        base_version_id=None,
        revision=1,
        state=VersionState.DRAFT,
        content_hash=content_hash(items, decisions, proposal.out_of_scope),
        run_id=proposal.run_id,
        source_version_ids=proposal.source_version_ids,
        items=items,
        decisions=decisions,
        out_of_scope=proposal.out_of_scope,
        created_by=proposal.created_by,
        created_at=now,
        set_aside=proposal.set_aside,
    )
