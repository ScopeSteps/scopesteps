from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from scopesteps.backlog.client import (
    AcceptanceCriterion,
    BacklogItem,
    BacklogVersionId,
    Blocker,
    CheckCode,
    ClaimOrigin,
    CriterionId,
    DecisionId,
    ItemId,
    SuggestionStatus,
)
from scopesteps.backlog.domain.editing import MAX_DECISION_ANSWER_CHARS
from scopesteps.evidence.client import EvidenceRef
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceVersionId

VersionState = Literal["draft", "in_review", "approved", "rejected"]


class BacklogDecision(BaseModel):
    """Something only a reviewer can settle. Unresolved until `status` is `answered`."""

    id: DecisionId
    kind: Literal["conflict", "missing_decision"]
    status: Literal["open", "skipped", "answered"]
    subject: str
    question: str
    why_it_matters: str
    evidence: list[EvidenceRef]
    affected_item_ids: list[ItemId]
    question_id: UUID | None = Field(
        description="The run's clarification question, if this was put to a reviewer."
    )
    answer: str | None
    decided_by: UserId | None = Field(description="Who answered or skipped it.")
    decided_at: datetime | None


class ScopeNoteResponse(BaseModel):
    """Work the sources rule out (`excluded`) or only suggest (`suggested`). Not in the backlog."""

    kind: Literal["excluded", "suggested"]
    summary: str
    evidence: list[EvidenceRef]


class BacklogVersionResponse(BaseModel):
    id: BacklogVersionId
    project_id: ProjectId
    base_version_id: BacklogVersionId | None
    revision: int
    state: VersionState
    content_hash: str
    run_id: UUID | None = Field(description="The agent run that proposed this version.")
    source_version_ids: list[SourceVersionId]
    items: list[BacklogItem]
    decisions: list[BacklogDecision]
    out_of_scope: list[ScopeNoteResponse]
    blockers: list[Blocker] = Field(
        description="Every blocker, including those that affect no item. Each item repeats its own."
    )
    created_at: datetime


class VersionDecisionResponse(BaseModel):
    decision: Literal["approved", "rejected"]
    decided_by: UserId = Field(description="The approver, or who rejected it.")
    decided_at: datetime


class BacklogVersionSummary(BaseModel):
    """A version without its content, as the history lists it."""

    id: BacklogVersionId
    number: int | None = Field(
        description="The baseline number of an approved version: 1 for v1, 2 for v2. Null for "
        "drafts and rejections."
    )
    state: VersionState
    revision: int
    content_hash: str
    base_version_id: BacklogVersionId | None = Field(
        description="The baseline this version was made from; null for the first draft."
    )
    run_id: UUID | None = Field(description="The agent run that proposed this version.")
    created_by: UserId
    created_at: datetime
    decision: VersionDecisionResponse | None = Field(
        description="How the version was decided; null while it is a draft or in review."
    )


class BacklogVersionPage(BaseModel):
    versions: list[BacklogVersionSummary] = Field(description="Newest first.")
    next_cursor: str | None = Field(
        description="Send as `cursor` to read the next, older page. Null on the last page."
    )


class CriterionChangeResponse(BaseModel):
    kind: Literal["added", "removed", "modified"]
    criterion_id: CriterionId
    before: AcceptanceCriterion | None
    after: AcceptanceCriterion | None


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


class VersionComparisonResponse(BaseModel):
    """What changes from `base` to `candidate`, matched by stable item and criterion ids. Each
    version is compared as its approval freezes it, so rejected suggestions count as absent."""

    base_version_id: BacklogVersionId
    base_content_hash: str
    candidate_version_id: BacklogVersionId
    candidate_content_hash: str
    operations: list[ItemChangeResponse] = Field(
        description="Items in the candidate's order, then removed items. Empty when nothing "
        "changed."
    )


# Bounds on what one request may carry; titles have their own limit in the domain.
MAX_DESCRIPTION_CHARS = 4000
MAX_CRITERION_CHARS = 1000
MAX_CRITERIA_PER_ITEM = 30


class CriterionPatch(BaseModel):
    id: CriterionId | None = Field(
        default=None, description="An existing criterion of the item; null adds a new one."
    )
    text: str = Field(min_length=1, max_length=MAX_CRITERION_CHARS)
    suggestion: SuggestionStatus | None = Field(
        default=None,
        description="Accept, reject or reopen (pending) an agent suggestion. Null leaves its "
        "status as it is; editing a suggestion's text accepts it.",
    )


class ItemPatchRequest(BaseModel):
    """Fields left unset are unchanged. Only draft versions accept edits."""

    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_CHARS)
    criteria: list[CriterionPatch] | None = Field(
        default=None,
        max_length=MAX_CRITERIA_PER_ITEM,
        description="The item's whole new list of criteria, in order. A criterion left out is "
        "removed; to keep a suggestion out of the approved version, reject it instead.",
    )


class DecisionAnswerRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    # A loose bound that only stops a huge body; the exact limit is checked after trimming.
    answer: str = Field(
        max_length=2 * MAX_DECISION_ANSWER_CHARS,
        description="The reviewer's answer. It settles an open or skipped decision.",
    )


class ReviewRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class CheckResponse(BaseModel):
    code: CheckCode
    title: str = Field(description="What the check confirms, e.g. 'Every citation resolves'.")
    passed: bool
    problems: list[str] = Field(description="Up to 10 of the problems found, ids and counts only.")
    problem_count: int


class ReviewResponse(BaseModel):
    """The result of every approval check on the version as it stands at `revision`."""

    version_id: BacklogVersionId
    revision: int
    state: VersionState
    content_hash: str
    base_version_id: BacklogVersionId | None
    baseline_version_id: BacklogVersionId | None = Field(
        description="The project's current baseline. Send it as `expected_baseline_id` when "
        "approving; approval needs the version's base to be this baseline."
    )
    epic_count: int
    story_count: int
    ready: bool = Field(description="A draft whose every check passed.")
    checks: list[CheckResponse]
    blockers: list[Blocker]


class ExportedCriterion(BaseModel):
    id: CriterionId
    text: str
    origin: ClaimOrigin = Field(
        description="source: stated by the cited passages. human: confirmed by a reviewer's "
        "answer. proposed: an agent suggestion an editor accepted. person: written by a person."
    )
    evidence: list[EvidenceRef]
    confirmed_by: list[DecisionId]


class ExportedItem(BaseModel):
    id: ItemId
    kind: Literal["epic", "story"]
    parent_id: ItemId | None = Field(description="The epic a story belongs to.")
    title: str
    description: str
    criteria: list[ExportedCriterion]
    assumptions: list[str]
    open_questions: list[str]
    human_edited: bool


class ExportedDecision(BaseModel):
    id: DecisionId
    kind: Literal["conflict", "missing_decision"]
    status: Literal["open", "skipped", "answered"]
    subject: str
    question: str
    why_it_matters: str
    answer: str | None
    decided_by: UserId | None
    decided_at: datetime | None
    affected_item_ids: list[ItemId]
    evidence: list[EvidenceRef]


class ExportedVersion(BaseModel):
    id: BacklogVersionId
    number: int | None = Field(description="The baseline number: 1 for v1, 2 for v2.")
    state: Literal["approved"]
    revision: int
    content_hash: str = Field(description="The hash the approval was bound to.")
    base_version_id: BacklogVersionId | None
    run_id: UUID | None
    source_version_ids: list[SourceVersionId]
    created_at: datetime
    approved_by: UserId
    approved_at: datetime


class ExportedProject(BaseModel):
    id: ProjectId
    name: str


class BacklogExport(BaseModel):
    """An approved version exactly as it was frozen, with the evidence the actor may see."""

    schema_version: Literal["scopesteps.backlog-export.v1"] = Field(
        description="Names this layout; a breaking change to it gets a new name."
    )
    exported_at: datetime
    project: ExportedProject
    version: ExportedVersion
    items: list[ExportedItem]
    decisions: list[ExportedDecision]
    out_of_scope: list[ScopeNoteResponse]
    withheld_evidence_count: int = Field(
        description="Citations left out because they no longer resolve to a passage the project "
        "holds. 0 when every citation is included."
    )
