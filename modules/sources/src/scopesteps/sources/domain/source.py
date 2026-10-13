from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceBlockId, SourceId, SourceVersionId


class SourceKind(StrEnum):
    """The two initial documents of a project. A project has one source of each kind."""

    BRIEF = "brief"
    TRANSCRIPT = "transcript"


class MediaType(StrEnum):
    PLAIN_TEXT = "text/plain"
    MARKDOWN = "text/markdown"


@dataclass(frozen=True)
class Source:
    """A document's identity. Its content lives in immutable versions."""

    id: SourceId
    project_id: ProjectId
    kind: SourceKind
    created_at: datetime


@dataclass(frozen=True)
class SourceVersion:
    """Immutable: corrected content becomes the next version, so earlier citations stay valid."""

    id: SourceVersionId
    source_id: SourceId
    project_id: ProjectId
    kind: SourceKind
    version: int
    filename: str
    media_type: MediaType
    checksum_sha256: str
    byte_size: int
    word_count: int
    block_count: int
    uploaded_by: UserId
    created_at: datetime


@dataclass(frozen=True)
class SourceBlock:
    """A stored paragraph. Offsets index into the version's normalized text."""

    id: SourceBlockId
    source_version_id: SourceVersionId
    ordinal: int
    text: str
    start_offset: int
    end_offset: int
