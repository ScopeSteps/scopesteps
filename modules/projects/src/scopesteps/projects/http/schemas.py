from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from scopesteps.backlog.client import BacklogVersionId, ScopeState
from scopesteps.evidence.client import EvidenceRef
from scopesteps.identity.client import Role, UserId
from scopesteps.projects.client import (
    MAX_PERSON_NAME_CHARS,
    MAX_ROLE_CHARS,
    PersonId,
    ProjectId,
    StatedRights,
)


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
    max_words: int = Field(
        description="Across the project's current sources plus an upload (ADR 0009)."
    )


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


ConfirmedRightsValue = Literal["decides", "advises", "unknown"]


class ExtractedPersonResponse(BaseModel):
    """The agent's reading of the sources. Corrections never change it."""

    name: str
    role: str = Field(description="Empty when no source states a role.")
    said: str = Field(
        description="The agent's one-sentence summary of what the person said or asked for. "
        "Empty when they are only mentioned."
    )
    stated_rights: StatedRights = Field(
        description="A decision right a source states. `not_stated` unless `rights_evidence` "
        "shows where it is stated."
    )
    evidence: list[EvidenceRef] = Field(description="Where the sources name or quote the person.")
    rights_evidence: list[EvidenceRef] = Field(
        description="Where a source states the decision right; empty when none is stated."
    )
    run_id: UUID = Field(description="The latest agent run that named this person.")
    extracted_at: datetime


class CorrectionResponse(BaseModel):
    name: str | None = Field(description="Null when the name was not corrected.")
    role: str | None = Field(description="Null when the role was not corrected.")
    corrected_by: UserId
    corrected_at: datetime


class ConfirmedRightsResponse(BaseModel):
    rights: ConfirmedRightsValue
    confirmed_by: UserId
    confirmed_at: datetime


class PersonResponse(BaseModel):
    id: PersonId
    project_id: ProjectId
    revision: int = Field(description="Send it back as `expected_revision` when changing them.")
    name: str = Field(description="The corrected name if there is one, otherwise the agent's.")
    role: str = Field(description="The corrected role if there is one, otherwise the agent's.")
    extracted: ExtractedPersonResponse
    correction: CorrectionResponse | None = Field(
        description="Null until someone corrects the name or role."
    )
    confirmed_rights: ConfirmedRightsResponse | None = Field(
        description="Set by a person on the project, never by the agent. Null until confirmed."
    )
    created_at: datetime


class PeopleResponse(BaseModel):
    people: list[PersonResponse]


class CorrectionRequest(BaseModel):
    """The whole correction. Null, or the agent's own value, leaves that field uncorrected."""

    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=MAX_PERSON_NAME_CHARS)
    role: str | None = Field(default=None, max_length=MAX_ROLE_CHARS)


class RightsRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    rights: ConfirmedRightsValue
