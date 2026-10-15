from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId
from scopesteps.sources.application import upload
from scopesteps.sources.application.reading import versions_with_blocks
from scopesteps.sources.application.removal import SourceUsageReader, SourceUse, SourceUserKind
from scopesteps.sources.domain.blocks import (
    TextBlock,
    normalize_text,
    quote_key,
    quote_matches,
    split_into_blocks,
)
from scopesteps.sources.domain.errors import SourceRemovedError
from scopesteps.sources.domain.ids import SourceBlockId, SourceId, SourceVersionId
from scopesteps.sources.infrastructure.repository import SqlSourceRepository


@dataclass(frozen=True)
class SourcePassage:
    """A stored paragraph as other modules see it. Versions are immutable, so callers may pin them."""

    block_id: SourceBlockId
    source_version_id: SourceVersionId
    source_kind: str
    filename: str
    ordinal: int
    text: str


def load_passages(
    session: Session, project_id: ProjectId, version_ids: Sequence[SourceVersionId]
) -> list[SourcePassage]:
    """Paragraphs of the given versions, version by version in the order given.

    Raises NotFoundError if a version does not belong to `project_id`. Callers check the actor's
    access to the project first.
    """
    return [
        SourcePassage(
            block_id=block.id,
            source_version_id=version.id,
            source_kind=version.kind.value,
            filename=version.filename,
            ordinal=block.ordinal,
            text=block.text,
        )
        for version, blocks in versions_with_blocks(
            SqlSourceRepository(session), project_id, version_ids
        )
        for block in blocks
    ]


def removed_versions(
    session: Session, project_id: ProjectId, version_ids: Collection[SourceVersionId]
) -> set[SourceVersionId]:
    """Which of the versions belong to a source the project has removed (ADR 0009).

    Their paragraphs stay readable through `load_passages`, but new work must not pin them.
    """
    return SqlSourceRepository(session).removed_version_ids(project_id, version_ids)


def current_version_ids(session: Session, project_id: ProjectId) -> list[SourceVersionId]:
    """The newest version of each source the project has not removed, in source order. Performs
    no access check."""
    return [version.id for version in SqlSourceRepository(session).current_versions(project_id)]


def record_change_request(
    session: Session, project_id: ProjectId, text: str, recorded_by: UserId, now: datetime
) -> SourceVersionId:
    """Store a change request's text as an immutable source version in the caller's
    transaction, so a change can cite it like any paragraph.

    It is not one of the project's current sources: it is not listed, counted against the word
    limit, matched as a duplicate or pinned by new work, and it cannot be versioned or removed.
    Its paragraphs are read by id like any version's. Performs no access check and records no
    audit event: the caller does both.
    """
    return upload.record_change_request(
        SqlSourceRepository(session), project_id, text, recorded_by, now
    ).id


def get_source_usage_reader() -> SourceUsageReader:
    """FastAPI dependency for the route that removes a source.

    Runs, backlog versions and people live in modules that build on this one, so they cannot be
    imported here; the composition root binds a reader that asks each of them.
    """
    raise RuntimeError("get_source_usage_reader is not bound to the modules that cite sources")


__all__ = [
    "SourceBlockId",
    "SourceId",
    "SourcePassage",
    "SourceRemovedError",
    "SourceUsageReader",
    "SourceUse",
    "SourceUserKind",
    "SourceVersionId",
    "TextBlock",
    "current_version_ids",
    "get_source_usage_reader",
    "load_passages",
    "normalize_text",
    "quote_key",
    "quote_matches",
    "record_change_request",
    "removed_versions",
    "split_into_blocks",
]
