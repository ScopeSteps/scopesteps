from datetime import datetime

from pydantic import BaseModel, Field

from scopesteps.backlog.client import BacklogVersionId, ScopeState
from scopesteps.identity.client import Role
from scopesteps.projects.client import ProjectId


class ScopeStatusResponse(BaseModel):
    """Where the project's scope stands, derived from its backlog versions."""

    state: ScopeState = Field(
        description="candidate_in_review or draft_in_progress while work newer than the baseline "
        "is in flight; otherwise baseline if a version has been approved, else no_baseline."
    )
    baseline_version: int | None = Field(
        description="Number of the current baseline (1 for the first approved version). Set "
        "whenever a baseline exists, whatever the state."
    )
    baseline_version_id: BacklogVersionId | None
    open_version_id: BacklogVersionId | None = Field(
        description="The candidate in review or draft in progress that the state refers to."
    )


class ProjectResponse(BaseModel):
    id: ProjectId
    name: str
    roles: list[Role] = Field(
        description="Every role the actor holds in the project. Roles combine; none implies "
        "another."
    )
    revision: int = Field(description="Send back as expected_revision when renaming.")
    status: ScopeStatusResponse
    created_at: datetime


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]


class SourceLimitsResponse(BaseModel):
    max_bytes: int = Field(description="Per uploaded file.")
    max_words: int = Field(description="Across the documents of one upload.")


class RunLimitsSummary(BaseModel):
    max_turns: int
    max_tool_calls: int
    max_clarification_rounds: int


class BacklogLimitsResponse(BaseModel):
    max_epics: int
    max_stories: int


class ProjectLimitsResponse(BaseModel):
    """The ceilings the API enforces, so a client never has to hard-code them."""

    project_name_max_chars: int
    source: SourceLimitsResponse
    run: RunLimitsSummary
    backlog: BacklogLimitsResponse


class ProjectDetailResponse(ProjectResponse):
    limits: ProjectLimitsResponse


class CreateProjectRequest(BaseModel):
    name: str = Field(
        description="1 to 80 characters once trimmed. Runs of whitespace become one space."
    )


class RenameProjectRequest(BaseModel):
    name: str = Field(
        description="1 to 80 characters once trimmed. Runs of whitespace become one space."
    )
    expected_revision: int = Field(
        ge=1, description="The revision the caller last read. A stale one returns 409."
    )
