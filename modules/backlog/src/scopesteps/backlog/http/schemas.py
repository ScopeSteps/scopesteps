from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from scopesteps.backlog.client import (
    BacklogItem,
    BacklogVersionId,
    Blocker,
    CheckCode,
    CriterionId,
    DecisionId,
    ItemId,
    SuggestionStatus,
)
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
