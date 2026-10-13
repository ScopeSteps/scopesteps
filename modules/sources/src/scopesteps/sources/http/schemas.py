from datetime import datetime

from pydantic import BaseModel, Field

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


class SourceVersionResponse(BaseModel):
    id: SourceVersionId
    source_id: SourceId
    project_id: ProjectId
    kind: SourceKind
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
