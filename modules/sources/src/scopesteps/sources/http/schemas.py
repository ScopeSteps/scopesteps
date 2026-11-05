from datetime import datetime

from pydantic import BaseModel, Field

from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceBlockId, SourceId, SourceVersionId
from scopesteps.sources.domain.source import MediaType, SourceKind


class BlockLocator(BaseModel):
    paragraph: int = Field(ge=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)


class SourceBlockResponse(BaseModel):
    id: SourceBlockId
    source_version_id: SourceVersionId
    ordinal: int = Field(ge=1)
    text: str
    locator: BlockLocator
    source_kind: SourceKind = Field(
        description="The kind of the source this paragraph is in, change requests included."
    )
    page: int | None = Field(
        ge=1, description="The PDF page the paragraph is on; null for other files."
    )
    start_ms: int | None = Field(
        ge=0,
        description=(
            "When a transcript paragraph was said, in milliseconds from the start of the "
            "meeting; null when the transcript gives no time."
        ),
    )
    speaker: str | None = Field(
        description=(
            "The speaker label a transcript paragraph starts with, as written; null for a "
            "paragraph that continues a turn and for other kinds."
        ),
    )


class SourceVersionResponse(BaseModel):
    id: SourceVersionId
    source_id: SourceId
    project_id: ProjectId
    kind: SourceKind
    source_number: int = Field(
        ge=1, description="Counts the project's sources from 1; never reused after a removal."
    )
    version: int = Field(ge=1)
    filename: str
    media_type: MediaType
    checksum_sha256: str
    word_count: int
    block_count: int
    created_at: datetime


class SourceUploadResponse(BaseModel):
    source_versions: list[SourceVersionResponse]


class SourceListResponse(BaseModel):
    source_versions: list[SourceVersionResponse]


class RemovedSourceResponse(BaseModel):
    source_id: SourceId
    project_id: ProjectId
    kind: SourceKind
    source_number: int = Field(ge=1)
    removed_at: datetime
    removed_by: UserId


class SpeakerLabelResponse(BaseModel):
    key: str = Field(description="The label as participants are matched against it.")
    label: str = Field(description="The label as first written in the transcript, plain text.")
    turn_count: int = Field(
        ge=1, description="Turns the speaker takes; consecutive labels by one speaker are one."
    )
    first_block_id: SourceBlockId
    first_paragraph: int = Field(ge=1)
    sample: str = Field(description="The start of the speaker's first turn, as plain text.")


class SourceSpeakersResponse(BaseModel):
    source_id: SourceId
    source_version_id: SourceVersionId = Field(description="The source's current version.")
    source_kind: SourceKind
    speakers: list[SpeakerLabelResponse] = Field(
        description="In order of first appearance; empty unless the source is a transcript."
    )
