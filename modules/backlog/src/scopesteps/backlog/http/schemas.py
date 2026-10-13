from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from scopesteps.backlog.client import (
    AcceptanceCriterion,
    BacklogItem,
    BacklogVersionId,
    Blocker,
    DecisionId,
    ItemId,
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


class ItemPatchRequest(BaseModel):
    """Fields left unset are unchanged. Only draft versions accept edits."""

    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    criteria: list[AcceptanceCriterion] | None = None


class ReviewRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class ReviewResponse(BaseModel):
    version_id: BacklogVersionId
    revision: int
    state: VersionState
    blockers: list[Blocker]
