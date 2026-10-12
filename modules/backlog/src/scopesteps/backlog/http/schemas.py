from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from scopesteps.backlog.client import AcceptanceCriterion, BacklogItem, BacklogVersionId, ItemId
from scopesteps.projects.client import ProjectId

VersionState = Literal["draft", "in_review", "approved", "rejected"]


class BacklogVersionResponse(BaseModel):
    id: BacklogVersionId
    project_id: ProjectId
    base_version_id: BacklogVersionId | None
    revision: int
    state: VersionState
    content_hash: str
    items: list[BacklogItem]
    created_at: datetime


class ItemPatchRequest(BaseModel):
    """Fields left unset are unchanged. Only draft versions accept edits."""

    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    criteria: list[AcceptanceCriterion] | None = None


class ReviewRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class Blocker(BaseModel):
    item_id: ItemId | None
    code: str
    message: str


class ReviewResponse(BaseModel):
    version_id: BacklogVersionId
    revision: int
    state: VersionState
    blockers: list[Blocker]
