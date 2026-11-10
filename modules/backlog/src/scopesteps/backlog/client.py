from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.application import candidates, changes, editing, tasks
from scopesteps.backlog.domain import version as domain
from scopesteps.backlog.domain.candidate import (
    CandidateProposal,
    CandidateRejectedError,
    ProposedCriterion,
    ProposedDecision,
    ProposedItem,
)
from scopesteps.backlog.domain.change import (
    BuiltChange,
    ChangeDecision,
    ChangeProposal,
    ChangeRejectedError,
    CriterionEdit,
    ItemEdit,
    ItemRef,
    NewItem,
    TaskRewrite,
)
from scopesteps.backlog.domain.editing import VersionChangedError, VersionNotDraftError
from scopesteps.backlog.domain.export import jira_summary
from scopesteps.backlog.domain.history import ItemChange, compare_items
from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, DecisionId, ItemId, TaskId
from scopesteps.backlog.domain.review import CheckCode, CheckResult, cites_any
from scopesteps.backlog.domain.status import NO_VERSIONS, ScopeState, ScopeStatus, scope_status
from scopesteps.backlog.domain.tasks import (
    TaskFlagCode,
    TaskScope,
    restates_story,
    task_flag,
    task_scope,
)
from scopesteps.backlog.domain.version import (
    MAX_EPICS,
    MAX_STORIES,
    MAX_TASKS_PER_STORY,
    BacklogVersion,
    BlockerCode,
    ClaimOrigin,
    Criterion,
    Decision,
    DecisionKind,
    Evidence,
    Item,
    ScopeNote,
    ScopeOutcome,
    SetAsideNote,
    SuggestionStatus,
    Task,
    TaskOrigin,
    VersionState,
)
from scopesteps.backlog.domain.version_decision import DecisionReader, VersionDecision
from scopesteps.backlog.infrastructure.repository import SqlVersionRepository
from scopesteps.evidence.client import Citation, EvidenceRef, InvalidCitation, check_citations
from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceBlockId, SourceVersionId


class Blocker(BaseModel):
    """A reason scope cannot be approved yet. `item_id` is null when no item is affected."""

    code: BlockerCode
    message: str
    item_id: ItemId | None
    decision_id: DecisionId | None = None
    criterion_id: CriterionId | None = None
    task_id: TaskId | None = None


class TaskFlagResponse(BaseModel):
    code: TaskFlagCode = Field(
        description="out_of_scope_work: names work the version leaves out of scope. "
        "new_work: names something no epic or story of the version mentions."
    )
    message: str = Field(description="Why, in plain words, for the person reviewing the task.")


class StoryTask(BaseModel):
    """A step of work under a story. `id` is stable across versions."""

    id: TaskId
    title: str = Field(min_length=1, max_length=200)
    origin: TaskOrigin = Field(
        description='suggested: the agent wrote it; show "Suggested by AI". person: written by a '
        "person."
    )
    suggestion: SuggestionStatus | None = Field(
        default=None,
        description="Set exactly for a suggested task: pending until a person accepts or edits "
        "it. A pending one blocks approval; one nobody wants is deleted.",
    )
    edited_by: UserId | None = None
    flag: TaskFlagResponse | None = Field(
        description="Set when code finds the task brings in work the backlog does not cover. "
        "Worked out on every read; it never blocks approval."
    )


class AcceptanceCriterion(BaseModel):
    id: CriterionId
    text: str = Field(min_length=1)
    origin: ClaimOrigin = Field(
        description="source: stated by the cited passages. human: confirmed by a reviewer's "
        "answer. proposed: an agent suggestion with no source. person: added by a person."
    )
    evidence: list[EvidenceRef] = []
    confirmed_by: list[DecisionId] = Field(
        default=[], description="The answered decisions that confirm a human-origin criterion."
    )
    suggestion: SuggestionStatus | None = Field(
        default=None,
        description="Set exactly for an agent suggestion (origin proposed): pending until an "
        "editor accepts or rejects it. Rejected suggestions are left out of an approved version.",
    )
    edited_by: UserId | None = Field(
        default=None, description="The person who last wrote the text, if a person did."
    )


class BacklogItem(BaseModel):
    """An epic or story. `id` is stable across versions; edits never reuse it for new work."""

    id: ItemId
    kind: Literal["epic", "story"]
    parent_id: ItemId | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    criteria: list[AcceptanceCriterion] = []
    assumptions: list[str] = []
    open_questions: list[str] = []
    tasks: list[StoryTask] = Field(
        default=[], description="A story's tasks in the order the team does them; none on an epic."
    )
    blockers: list[Blocker] = []
    human_edited: bool = Field(
        default=False, description="A person changed the title, description, criteria or tasks."
    )
    edited_by: UserId | None = Field(default=None, description="Who last changed the item.")
    edited_at: datetime | None = None


class CriterionChangeResponse(BaseModel):
    kind: Literal["added", "removed", "modified"]
    criterion_id: CriterionId
    before: AcceptanceCriterion | None
    after: AcceptanceCriterion | None


class TaskChangeResponse(BaseModel):
    kind: Literal["added", "removed", "modified"]
    task_id: TaskId
    before: StoryTask | None
    after: StoryTask | None


class ItemChangeResponse(BaseModel):
    """One item's change, shaped like a change set's operation."""

    kind: Literal["add_item", "modify_item", "remove_item"]
    item_id: ItemId
    before: BacklogItem | None = Field(description="Null for an added item.")
    after: BacklogItem | None = Field(description="Null for a removed item.")
    changed_fields: list[
        Literal["kind", "parent_id", "title", "description", "assumptions", "open_questions"]
    ] = Field(description="The item's own fields that differ; criteria are listed apart.")
    criteria: list[CriterionChangeResponse] = Field(
        description="Criteria added, removed or changed, matched by their stable ids."
    )
    tasks: list[TaskChangeResponse] = Field(
        default=[], description="Tasks added, removed or reworded, matched by their stable ids."
    )


def evidence_refs(evidence: Sequence[Evidence]) -> list[EvidenceRef]:
    return [
        EvidenceRef(
            source_version_id=SourceVersionId(e.source_version_id),
            block_id=SourceBlockId(e.block_id),
            quote=e.quote,
            relationship=e.relationship,
        )
        for e in evidence
    ]


def blocker_response(blocker: domain.Blocker) -> Blocker:
    return Blocker(
        code=blocker.code,
        message=blocker.message,
        item_id=blocker.item_id,
        decision_id=blocker.decision_id,
        criterion_id=blocker.criterion_id,
        task_id=blocker.task_id,
    )


def criterion_response(criterion: Criterion) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        id=criterion.id,
        text=criterion.text,
        origin=criterion.origin,
        evidence=evidence_refs(criterion.evidence),
        confirmed_by=list(criterion.confirmed_by),
        suggestion=criterion.suggestion,
        edited_by=criterion.edited_by,
    )


def task_response(task: Task, scope: TaskScope) -> StoryTask:
    flag = task_flag(task, scope)
    return StoryTask(
        id=task.id,
        title=task.title,
        origin=task.origin,
        suggestion=task.suggestion,
        edited_by=task.edited_by,
        flag=None if flag is None else TaskFlagResponse(code=flag.code, message=flag.message),
    )


def item_response(
    item: Item,
    version: BacklogVersion,
    blockers: Sequence[Blocker] | None = None,
    scope: TaskScope | None = None,
) -> BacklogItem:
    """An item as the API shows it, with the blockers it has in `version`. Pass the version's
    `task_scope` when showing many items, so it is worked out once."""
    all_blockers = (
        blockers if blockers is not None else [blocker_response(b) for b in version.blockers()]
    )
    checked = scope or task_scope(version.items, version.out_of_scope)
    return BacklogItem(
        id=item.id,
        kind=item.kind,
        parent_id=item.parent_id,
        title=item.title,
        description=item.description,
        criteria=[criterion_response(criterion) for criterion in item.criteria],
        assumptions=list(item.assumptions),
        open_questions=list(item.open_questions),
        tasks=[task_response(task, checked) for task in item.tasks],
        blockers=[blocker for blocker in all_blockers if blocker.item_id == item.id],
        human_edited=item.human_edited,
        edited_by=item.edited_by,
        edited_at=item.edited_at,
    )


def item_change_responses(
    base: BacklogVersion, candidate: BacklogVersion, changes: Sequence[ItemChange]
) -> list[ItemChangeResponse]:
    base_scope = task_scope(base.items, base.out_of_scope)
    candidate_scope = task_scope(candidate.items, candidate.out_of_scope)
    return [
        ItemChangeResponse(
            kind=change.kind,
            item_id=change.item_id,
            before=None
            if change.before is None
            else item_response(change.before, base, scope=base_scope),
            after=None
            if change.after is None
            else item_response(change.after, candidate, scope=candidate_scope),
            changed_fields=list(change.changed_fields),
            criteria=[
                CriterionChangeResponse(
                    kind=criterion.kind,
                    criterion_id=criterion.criterion_id,
                    before=None
                    if criterion.before is None
                    else criterion_response(criterion.before),
                    after=None if criterion.after is None else criterion_response(criterion.after),
                )
                for criterion in change.criteria
            ],
            tasks=[
                TaskChangeResponse(
                    kind=task.kind,
                    task_id=task.task_id,
                    before=None if task.before is None else task_response(task.before, base_scope),
                    after=None
                    if task.after is None
                    else task_response(task.after, candidate_scope),
                )
                for task in change.tasks
            ],
        )
        for change in changes
    ]


def _citation_checker(session: Session) -> candidates.CitationChecker:
    def check(project_id: ProjectId, citations: Sequence[Citation]) -> list[InvalidCitation]:
        return check_citations(session, project_id, citations)

    return check


def candidate_problems(session: Session, proposal: CandidateProposal) -> list[str]:
    """Why `proposal` would be rejected; empty when `save_candidate` will accept it."""
    return candidates.candidate_problems(_citation_checker(session), proposal)


def save_candidate(
    session: Session, proposal: CandidateProposal, now: datetime
) -> BacklogVersionId:
    """Save a run's candidate as a draft version in the caller's transaction, at most once per run.

    Nothing here approves anything: the version stays a draft until a reviewer acts on it. A
    newly saved version is recorded in the activity log as the agent's action. Raises
    CandidateRejectedError, saving nothing, if the proposal fails validation.
    """
    version = candidates.save_candidate(
        SqlVersionRepository(session),
        audit_recorder(session),
        _citation_checker(session),
        proposal,
        now,
    )
    return version.id


def find_candidate(session: Session, run_id: UUID) -> BacklogVersionId | None:
    return SqlVersionRepository(session).find_id_by_run(run_id)


@dataclass(frozen=True)
class ScopeDecisionState:
    """A required scope decision on a change candidate, and what an approver chose, if anyone has."""

    id: DecisionId
    outcome: ScopeOutcome | None


@dataclass(frozen=True)
class VersionSummary:
    """What a decision on a version needs to know about it, without its content."""

    id: BacklogVersionId
    project_id: ProjectId
    base_version_id: BacklogVersionId | None
    revision: int
    state: VersionState
    content_hash: str
    epics: int
    stories: int
    scope_decisions: tuple[ScopeDecisionState, ...] = ()
    """The version's scope_reversal decisions (ADR 0011); only change candidates have any."""


def load_version_summary(session: Session, version_id: BacklogVersionId) -> VersionSummary | None:
    """Performs no access check: the caller resolves access to the returned project."""
    version = SqlVersionRepository(session).get(version_id)
    if version is None:
        return None
    epics = sum(1 for item in version.items if item.kind == "epic")
    return VersionSummary(
        id=version.id,
        project_id=version.project_id,
        base_version_id=version.base_version_id,
        revision=version.revision,
        state=version.state,
        content_hash=version.content_hash,
        epics=epics,
        stories=len(version.items) - epics,
        scope_decisions=tuple(
            ScopeDecisionState(d.id, d.scope_outcome)
            for d in version.decisions
            if d.kind == "scope_reversal"
        ),
    )


def approval_checks(session: Session, version_id: BacklogVersionId) -> tuple[CheckResult, ...]:
    """Every approval check on the version's stored content, run now."""
    version = SqlVersionRepository(session).get(version_id)
    if version is None:
        raise NotFoundError("Backlog version not found")
    return editing.run_checks(_citation_checker(session), version)


def freeze_approved(
    session: Session,
    version_id: BacklogVersionId,
    *,
    expected_revision: int,
    content_hash: str,
    expected_state: VersionState = VersionState.DRAFT,
) -> bool:
    """Make the draft (or change candidate in review) an approved, unchangeable version in the
    caller's transaction, leaving out its rejected suggestions. False, changing nothing, if it is
    no longer in `expected_state` at exactly that revision and hash."""
    return SqlVersionRepository(session).freeze_approved(
        version_id,
        expected_revision=expected_revision,
        content_hash=content_hash,
        expected_state=expected_state,
    )


def mark_rejected(
    session: Session,
    version_id: BacklogVersionId,
    *,
    expected_revision: int,
    expected_state: VersionState = VersionState.DRAFT,
) -> bool:
    """Mark the draft (or change candidate in review) rejected in the caller's transaction.
    False, changing nothing, if it is no longer in `expected_state` at that revision."""
    return SqlVersionRepository(session).mark_rejected(
        version_id, expected_revision=expected_revision, expected_state=expected_state
    )


def load_scope_statuses(
    session: Session, project_ids: Collection[ProjectId]
) -> dict[ProjectId, ScopeStatus]:
    """Where each project's scope stands, for every id given, in one query.

    Performs no access check: callers pass only projects the actor may see.
    """
    headers = SqlVersionRepository(session).headers_by_project(project_ids)
    return {
        project_id: scope_status(headers[project_id]) if project_id in headers else NO_VERSIONS
        for project_id in project_ids
    }


@dataclass(frozen=True)
class ItemSummary:
    """An epic or story as other modules name it."""

    id: ItemId
    kind: Literal["epic", "story"]
    title: str
    """From the newest version that has the item."""
    in_current_backlog: bool
    """Whether the version in flight, or else the baseline, still has it."""


def current_version_id(session: Session, project_id: ProjectId) -> BacklogVersionId | None:
    """The version in flight, or else the baseline; None before the first draft. Performs no
    access check."""
    status = load_scope_statuses(session, [project_id])[project_id]
    return status.open_version_id or status.baseline_version_id


def describe_items(
    session: Session, project_id: ProjectId, item_ids: Collection[ItemId]
) -> dict[ItemId, ItemSummary]:
    """The project's items among `item_ids`, in any version, in two queries; ids the project
    never had are absent. Item ids are stable across versions. Performs no access check."""
    if not item_ids:
        return {}
    current = current_version_id(session, project_id)
    return {
        item_id: ItemSummary(
            id=item_id,
            kind="epic" if kind == "epic" else "story",
            title=title,
            in_current_backlog=current in versions,
        )
        for item_id, (kind, title, versions) in SqlVersionRepository(session)
        .latest_item_rows(project_id, item_ids)
        .items()
    }


def draft_blocker_counts(
    session: Session, version_ids: Collection[BacklogVersionId]
) -> dict[BacklogVersionId, int]:
    """How many blockers each version given has, for those that are still drafts, in two queries
    however many versions. A draft with none is ready for an approver, who still runs every
    approval check. Performs no access check."""
    return {
        version.id: len(version.blockers())
        for version in SqlVersionRepository(session).get_many(version_ids)
        if version.state is VersionState.DRAFT
    }


def versions_citing_sources(
    session: Session, project_id: ProjectId, source_version_ids: Collection[UUID]
) -> list[BacklogVersionId]:
    """The project's backlog versions, in any state, made from or citing any of the source
    versions. Performs no access check."""
    return [
        version.id
        for version in SqlVersionRepository(session).in_project(project_id)
        if cites_any(version, source_version_ids)
    ]


@dataclass(frozen=True)
class OutlineItem:
    kind: Literal["epic", "story"]
    title: str
    description: str
    criteria: tuple[str, ...]
    parent_title: str | None
    id: ItemId | None = None
    parent_id: ItemId | None = None
    tasks: tuple[str, ...] = ()
    """A story's tasks a person wrote or accepted; suggestions nobody reviewed are left out."""


@dataclass(frozen=True)
class OutlineDecision:
    """A decision nobody has answered yet, with the items it blocks."""

    id: DecisionId
    subject: str
    question: str
    affected_item_ids: tuple[ItemId, ...]
    kind: DecisionKind = "missing_decision"
    """A `scope_reversal` is settled by reverse or keep, never by a written answer."""


@dataclass(frozen=True)
class BacklogOutline:
    """A version's content in reading form, for describing the backlog without its evidence."""

    version_id: BacklogVersionId
    state: VersionState
    items: tuple[OutlineItem, ...]
    open_decisions: tuple[str, ...]
    """The subjects of the decisions nobody has answered yet."""
    decisions: tuple[OutlineDecision, ...] = ()
    """The same decisions as `open_decisions`, with their ids, questions and affected items."""
    revision: int = 1
    out_of_scope: tuple[str, ...] = ()
    """What the sources rule out or only suggest, by summary."""


def current_backlog(session: Session, project_id: ProjectId) -> BacklogOutline | None:
    """The newest version in flight, or else the baseline; None if neither exists. Rejected
    suggestions are left out. Performs no access check."""
    status = load_scope_statuses(session, [project_id])[project_id]
    version_id = status.open_version_id or status.baseline_version_id
    version = None if version_id is None else SqlVersionRepository(session).get(version_id)
    return None if version is None else outline_of(version)


def outline_of(version: BacklogVersion) -> BacklogOutline:
    """`version` in reading form, without evidence or rejected suggestions."""
    titles = {item.id: item.title for item in version.items}
    unresolved = [d for d in version.decisions if not d.is_resolved]
    return BacklogOutline(
        version_id=version.id,
        state=version.state,
        items=tuple(
            OutlineItem(
                kind=item.kind,
                title=item.title,
                description=item.description,
                criteria=tuple(c.text for c in item.criteria if c.suggestion != "rejected"),
                parent_title=None if item.parent_id is None else titles.get(item.parent_id),
                id=item.id,
                parent_id=item.parent_id,
                tasks=tuple(t.title for t in item.tasks if t.suggestion != "pending"),
            )
            for item in version.items
        ),
        open_decisions=tuple(d.subject for d in unresolved),
        decisions=tuple(
            OutlineDecision(d.id, d.subject, d.question, d.affected_item_ids, d.kind)
            for d in unresolved
        ),
        revision=version.revision,
        out_of_scope=tuple(note.summary for note in version.out_of_scope),
    )


def load_outline(session: Session, version_id: BacklogVersionId) -> BacklogOutline | None:
    """`outline_of` the version, or None if there is none. Performs no access check."""
    version = SqlVersionRepository(session).get(version_id)
    return None if version is None else outline_of(version)


def save_task_suggestions(
    session: Session,
    version_id: BacklogVersionId,
    suggested: Mapping[ItemId, Sequence[str]],
    *,
    run_id: UUID,
    now: datetime,
) -> tasks.SavedSuggestions:
    """Put the agent's suggested task titles under each story of a draft, as one revision, in
    the caller's transaction (see `application/tasks.py`). Raises VersionNotDraftError once the
    version is no longer a draft, so a suggestion never lands on an approved version, and
    VersionChangedError when the draft was saved meanwhile. Performs no access check."""
    return tasks.save_task_suggestions(
        SqlVersionRepository(session),
        audit_recorder(session),
        version_id,
        suggested,
        run_id=run_id,
        now=now,
    )


def task_restates_story(story: OutlineItem, task_title: str) -> bool:
    """Whether a task only says its story again (see `domain/tasks.py`)."""
    item = Item(
        id=story.id or ItemId(UUID(int=0)),
        kind="story",
        parent_id=None,
        title=story.title,
        description=story.description,
    )
    return restates_story(item, task_title)


def task_scope_problem(
    task_title: str, backlog: Sequence[OutlineItem], out_of_scope: Sequence[str]
) -> str | None:
    """Why a task looks like work the backlog does not cover, in plain words, or None: the same
    check the API shows on every task, for the agent's run and the evaluation harness."""
    items = [
        Item(
            id=item.id or ItemId(UUID(int=0)),
            kind=item.kind,
            parent_id=None,
            title=item.title,
            description=item.description,
            criteria=tuple(
                Criterion(CriterionId(UUID(int=0)), text, "person") for text in item.criteria
            ),
        )
        for item in backlog
    ]
    scope = task_scope(items, [ScopeNote("excluded", summary) for summary in out_of_scope])
    flag = task_flag(Task(TaskId(UUID(int=0)), task_title, "suggested", "pending"), scope)
    return None if flag is None else flag.message


def change_run_answer(
    session: Session,
    run_id: UUID,
    question_id: UUID,
    answer: str,
    *,
    decided_by: UserId,
    now: datetime,
) -> BacklogVersionId | None:
    """Put a changed clarification answer into the draft made from `run_id`, in the caller's
    transaction, moving the draft to its next revision.

    None when no version was made from the run. Raises VersionNotDraftError once that version is
    no longer a draft (its answers are locked), and VersionChangedError if it changed meanwhile.
    The caller checks access and records the action.
    """
    version = editing.change_run_answer(
        SqlVersionRepository(session), run_id, question_id, answer, decided_by=decided_by, now=now
    )
    return None if version is None else version.id


def load_version(session: Session, version_id: BacklogVersionId) -> BacklogVersion | None:
    """A version with its whole content. Performs no access check: the caller resolves access to
    the returned project."""
    return SqlVersionRepository(session).get(version_id)


def current_baseline_id(session: Session, project_id: ProjectId) -> BacklogVersionId | None:
    """The project's newest approved version. Performs no access check."""
    return load_scope_statuses(session, [project_id])[project_id].baseline_version_id


def change_candidate_problems(session: Session, proposal: ChangeProposal) -> list[str]:
    """Why `proposal` would be refused; empty when `save_change_candidate` will accept it."""
    return changes.change_candidate_problems(
        SqlVersionRepository(session),
        lambda project_id: current_baseline_id(session, project_id),
        _citation_checker(session),
        proposal,
    )


@dataclass(frozen=True)
class SavedChange:
    version_id: BacklogVersionId
    item_ids: dict[str, ItemId]
    """The id each new item's ref received."""
    decision_ids: dict[str, DecisionId]
    """The id each decision's key received."""


def save_change_candidate(session: Session, proposal: ChangeProposal, now: datetime) -> SavedChange:
    """Save a change run's proposal in the caller's transaction as a candidate in review, built
    from the current baseline, at most once per run (ADR 0011).

    Items the proposal does not touch keep their ids, content and provenance. The baseline is
    only read. A candidate in review cannot be edited; only an approver's scope decisions change
    it before `change_control` approves or rejects it. Raises ChangeRejectedError, saving nothing, if the proposal fails validation, the
    baseline is no longer the current one or the run already proposed a candidate. The caller
    records the action.
    """
    built: BuiltChange = changes.save_change_candidate(
        SqlVersionRepository(session),
        lambda project_id: current_baseline_id(session, project_id),
        _citation_checker(session),
        proposal,
        now,
    )
    return SavedChange(built.version.id, built.item_ids, built.decision_ids)


def compare_versions(base: BacklogVersion, candidate: BacklogVersion) -> tuple[ItemChange, ...]:
    """What changes from `base` to `candidate`, by stable item and criterion ids."""
    return compare_items(base.items, candidate.items)


def approved_items(version: BacklogVersion) -> tuple[Item, ...]:
    """The version's items as approval freezes them, which is what `compare_versions` compares:
    rejected suggestions are left out."""
    return domain.approved_content(version.items)


def get_decision_reader() -> DecisionReader:
    """FastAPI dependency for the routes that show how a version was decided.

    `change_control` records approvals and rejections and builds on this module, so it cannot be
    imported here; the composition root binds its reader with `app.dependency_overrides`.
    """
    raise RuntimeError("get_decision_reader is not bound to change_control's decisions")


__all__ = [
    "MAX_EPICS",
    "MAX_STORIES",
    "MAX_TASKS_PER_STORY",
    "AcceptanceCriterion",
    "BacklogItem",
    "BacklogOutline",
    "BacklogVersion",
    "BacklogVersionId",
    "Blocker",
    "CandidateProposal",
    "CandidateRejectedError",
    "ChangeDecision",
    "ChangeProposal",
    "ChangeRejectedError",
    "CheckCode",
    "CheckResult",
    "ClaimOrigin",
    "Criterion",
    "CriterionChangeResponse",
    "CriterionEdit",
    "CriterionId",
    "Decision",
    "DecisionId",
    "DecisionKind",
    "DecisionReader",
    "Evidence",
    "Item",
    "ItemChange",
    "ItemChangeResponse",
    "ItemEdit",
    "ItemId",
    "ItemRef",
    "ItemSummary",
    "NewItem",
    "OutlineDecision",
    "OutlineItem",
    "ProposedCriterion",
    "ProposedDecision",
    "ProposedItem",
    "SavedChange",
    "ScopeDecisionState",
    "ScopeNote",
    "ScopeOutcome",
    "ScopeState",
    "ScopeStatus",
    "SetAsideNote",
    "StoryTask",
    "SuggestionStatus",
    "Task",
    "TaskChangeResponse",
    "TaskFlagResponse",
    "TaskId",
    "TaskOrigin",
    "TaskRewrite",
    "VersionChangedError",
    "VersionDecision",
    "VersionNotDraftError",
    "VersionState",
    "VersionSummary",
    "approval_checks",
    "approved_items",
    "blocker_response",
    "candidate_problems",
    "change_candidate_problems",
    "change_run_answer",
    "compare_versions",
    "criterion_response",
    "current_backlog",
    "current_baseline_id",
    "current_version_id",
    "describe_items",
    "draft_blocker_counts",
    "evidence_refs",
    "find_candidate",
    "freeze_approved",
    "get_decision_reader",
    "item_change_responses",
    "item_response",
    "jira_summary",
    "load_outline",
    "load_scope_statuses",
    "load_version",
    "load_version_summary",
    "mark_rejected",
    "outline_of",
    "save_candidate",
    "save_change_candidate",
    "save_task_suggestions",
    "task_restates_story",
    "task_scope_problem",
    "versions_citing_sources",
]
