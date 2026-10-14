from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId
from scopesteps.sources.domain.ids import SourceBlockId, SourceId, SourceVersionId


class SourceKind(StrEnum):
    """What a document is, chosen by the uploader. A project may hold any number of each kind."""

    BRIEF = "brief"
    TRANSCRIPT = "transcript"
    SUPPORTING_DOCUMENT = "supporting_document"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")


class MediaType(StrEnum):
    PLAIN_TEXT = "text/plain"
    MARKDOWN = "text/markdown"


@dataclass(frozen=True)
class Source:
    """A document's identity. Its content lives in immutable versions.

    `number` counts the project's sources from 1 and is never reused, so it can label a source.
    A removed source leaves the project's current set but keeps its versions (ADR 0009).
    """

    id: SourceId
    project_id: ProjectId
    kind: SourceKind
    number: int
    created_at: datetime
    removed_at: datetime | None = None
    removed_by: UserId | None = None

    @property
    def is_removed(self) -> bool:
        return self.removed_at is not None


@dataclass(frozen=True)
class SourceVersion:
    """Immutable: corrected content becomes the next version, so earlier citations stay valid."""

    id: SourceVersionId
    source_id: SourceId
    project_id: ProjectId
    kind: SourceKind
    source_number: int
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
