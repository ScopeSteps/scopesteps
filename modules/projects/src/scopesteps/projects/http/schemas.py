from datetime import datetime
from typing import Annotated, Literal
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


class ConversationLimitsResponse(BaseModel):
    max_message_chars: int = Field(description="Per message sent to the agent.")


class ProjectLimitsResponse(BaseModel):
    """The ceilings the API enforces, so a client never has to hard-code them."""

    project_name_max_chars: int
    source: SourceLimitsResponse
    run: RunLimitsSummary
    backlog: BacklogLimitsResponse
    conversation: ConversationLimitsResponse


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


class MeetingRoleResponse(BaseModel):
    value: str
    set_by: UserId
    set_at: datetime


SpeakerStatusValue = Literal["linked", "linked_automatically", "not_a_person", "unconfirmed"]


class SpokeInResponse(BaseModel):
    source_id: UUID
    label: str = Field(description="The speaker label in that transcript, as plain text.")
    status: Literal["linked", "linked_automatically"]


class PersonResponse(BaseModel):
    id: PersonId
    project_id: ProjectId
    revision: int = Field(description="Send it back as `expected_revision` when changing them.")
    origin: Literal["extracted", "confirmed_speaker"] = Field(
        description="`extracted` when a run first named the person, `confirmed_speaker` when an "
        "editor created them as a transcript's speaker."
    )
    name: str = Field(
        description="The corrected name if there is one, else the entered one, else the agent's."
    )
    role: str = Field(description="The corrected role if there is one, otherwise the agent's.")
    entered_name: str | None = Field(
        description="The name an editor gave when creating the person as a speaker."
    )
    meeting_role: MeetingRoleResponse | None = Field(
        description="What they do in the project's meetings, as an editor entered it."
    )
    spoke_in: list[SpokeInResponse] = Field(
        description="The current transcripts in which a speaker label is linked to them."
    )
    extracted: ExtractedPersonResponse | None = Field(
        description="The agent's reading; null until a run names the person."
    )
    correction: CorrectionResponse | None = Field(
        description="Null until someone corrects the name or role."
    )
    confirmed_rights: ConfirmedRightsResponse | None = Field(
        description="Set by a person on the project, never by the agent. Null until confirmed."
    )
    created_at: datetime


class UnconfirmedSpeakerResponse(BaseModel):
    source_id: UUID
    key: str
    label: str


class PeopleResponse(BaseModel):
    people: list[PersonResponse]
    unconfirmed_speakers: list[UnconfirmedSpeakerResponse] = Field(
        description="Speakers in current transcripts nobody has said who they are yet."
    )


class SpeakerResponse(BaseModel):
    key: str
    label: str = Field(description="As first written in the transcript, plain text.")
    turn_count: int = Field(ge=1)
    first_block_id: UUID
    first_paragraph: int = Field(ge=1)
    sample: str = Field(description="The start of the speaker's first turn, as plain text.")
    status: SpeakerStatusValue = Field(
        description="An editor's answer (`linked`, `not_a_person`), a link to a participant "
        "someone already confirmed (`linked_automatically`), or `unconfirmed`."
    )
    person_id: PersonId | None
    assigned_by: UserId | None = Field(description="Who gave the answer; null unless answered.")
    assigned_at: datetime | None


class TranscriptSpeakersResponse(BaseModel):
    source_id: UUID
    source_version_id: UUID = Field(description="The transcript's current version.")
    revision: int = Field(
        ge=0, description="Send it back as `expected_revision`; 0 until the first answer."
    )
    speakers: list[SpeakerResponse]


class ProjectSpeakersResponse(BaseModel):
    transcripts: list[TranscriptSpeakersResponse]


class LinkSpeakerAnswer(BaseModel):
    label_key: str
    choice: Literal["link"]
    person_id: PersonId
    meeting_role: str | None = Field(
        default=None,
        max_length=MAX_ROLE_CHARS,
        description="Sets the participant's meeting role; null keeps it, blank clears it.",
    )


class NewParticipantAnswer(BaseModel):
    label_key: str
    choice: Literal["new"]
    name: str = Field(max_length=MAX_PERSON_NAME_CHARS)
    meeting_role: str | None = Field(default=None, max_length=MAX_ROLE_CHARS)


class NotAPersonAnswer(BaseModel):
    label_key: str
    choice: Literal["not_a_person"]


SpeakerAnswer = Annotated[
    LinkSpeakerAnswer | NewParticipantAnswer | NotAPersonAnswer, Field(discriminator="choice")
]

# Far more labels than any meeting has speakers; it bounds the work one request can ask for.
MAX_SPEAKER_ANSWERS = 200


class SpeakerMappingRequest(BaseModel):
    """The whole answer for the transcript: a label left out goes back to unconfirmed."""

    expected_revision: int = Field(ge=0)
    speakers: list[SpeakerAnswer] = Field(max_length=MAX_SPEAKER_ANSWERS)


class CorrectionRequest(BaseModel):
    """The whole correction. Null, or the agent's own value, leaves that field uncorrected."""

    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=MAX_PERSON_NAME_CHARS)
    role: str | None = Field(default=None, max_length=MAX_ROLE_CHARS)


class RightsRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    rights: ConfirmedRightsValue
