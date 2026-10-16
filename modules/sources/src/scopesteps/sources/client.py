from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectId
from scopesteps.sources.application import upload
from scopesteps.sources.application.reading import versions_with_blocks
from scopesteps.sources.application.removal import SourceUsageReader, SourceUse, SourceUserKind
from scopesteps.sources.application.speakers import SourceSpeakers, labels_of
from scopesteps.sources.domain.blocks import (
    TextBlock,
    normalize_text,
    quote_key,
    quote_matches,
    split_into_blocks,
)
from scopesteps.sources.domain.errors import SourceRemovedError
from scopesteps.sources.domain.ids import SourceBlockId, SourceId, SourceVersionId
from scopesteps.sources.domain.source import SourceKind, SpeakerLabel
from scopesteps.sources.domain.speakers import detect_speakers, speakers_by_paragraph
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


def load_source_speakers(
    session: Session, project_id: ProjectId, source_id: SourceId
) -> SourceSpeakers:
    """The speaker labels in a source's current version, the only way other modules learn who
    speaks in a transcript: they never parse source text themselves (ADR 0012).

    Raises NotFoundError unless the source belongs to `project_id`. Performs no access check.
    """
    store = SqlSourceRepository(session)
    source = store.get_source(project_id, source_id)
    if source is None or source.kind is SourceKind.CHANGE_REQUEST:
        raise NotFoundError("Source not found")
    version = store.latest_version_of(source.id)
    return SourceSpeakers(source=source, version=version, speakers=labels_of(store, version)[0])


def load_current_speakers(session: Session, project_id: ProjectId) -> list[SourceSpeakers]:
    """The speaker labels in each of the project's current transcripts, in source order.
    Removed sources are left out. Performs no access check."""
    store = SqlSourceRepository(session)
    found: list[SourceSpeakers] = []
    for version in store.current_versions(project_id):
        source = store.get_source(project_id, version.source_id)
        if source is not None and version.kind is SourceKind.TRANSCRIPT:
            found.append(SourceSpeakers(source, version, labels_of(store, version)[0]))
    return found


def load_version_speakers(
    session: Session, project_id: ProjectId, version_id: SourceVersionId
) -> list[SpeakerLabel]:
    """The speaker labels in one version, for work pinned to it. Empty unless it is a transcript.

    Raises NotFoundError unless the version belongs to `project_id`. Performs no access check.
    """
    store = SqlSourceRepository(session)
    version = store.get_version(project_id, version_id)
    if version is None:
        raise NotFoundError("Source version not found")
    return labels_of(store, version)[0]


@dataclass(frozen=True)
class VersionSpeakers:
    """Who speaks where in one transcript version: each label by its key, as first written, and
    for each paragraph that holds speech the keys of its speakers in order."""

    source_id: SourceId
    source_version_id: SourceVersionId
    labels: dict[str, str]
    by_block: dict[SourceBlockId, tuple[str, ...]]


def load_speaker_turns(
    session: Session, project_id: ProjectId, version_ids: Sequence[SourceVersionId]
) -> list[VersionSpeakers]:
    """Speaker turns of the transcripts among `version_ids`, for work pinned to them; other kinds
    are left out. Found by the parser from the stored text, never by a model (ADR 0012).

    Raises NotFoundError if a version does not belong to `project_id`. Performs no access check.
    """
    store = SqlSourceRepository(session)
    found: list[VersionSpeakers] = []
    for version, blocks in versions_with_blocks(store, project_id, version_ids):
        if version.kind is not SourceKind.TRANSCRIPT:
            continue
        text = store.version_text(version.id)
        ordinals = {block.ordinal: block.id for block in blocks}
        found.append(
            VersionSpeakers(
                source_id=version.source_id,
                source_version_id=version.id,
                labels={label.key: label.label for label in labels_of(store, version)[0]},
                by_block={
                    ordinals[ordinal]: keys
                    for ordinal, keys in speakers_by_paragraph(text).items()
                    if ordinal in ordinals
                },
            )
        )
    return found


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
    "SourceSpeakers",
    "SourceUsageReader",
    "SourceUse",
    "SourceUserKind",
    "SourceVersionId",
    "SpeakerLabel",
    "TextBlock",
    "VersionSpeakers",
    "current_version_ids",
    "detect_speakers",
    "get_source_usage_reader",
    "load_current_speakers",
    "load_passages",
    "load_source_speakers",
    "load_speaker_turns",
    "load_version_speakers",
    "normalize_text",
    "quote_key",
    "quote_matches",
    "record_change_request",
    "removed_versions",
    "speakers_by_paragraph",
    "split_into_blocks",
]
