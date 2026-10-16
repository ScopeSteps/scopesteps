from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from scopesteps.identity.client import ProjectAccess
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectId
from scopesteps.sources.domain.ids import SourceId, SourceVersionId
from scopesteps.sources.domain.source import (
    Source,
    SourceBlock,
    SourceKind,
    SourceVersion,
    SpeakerLabel,
)
from scopesteps.sources.domain.speakers import speaker_labels


class SpeakerReader(Protocol):
    def get_source(self, project_id: ProjectId, source_id: SourceId) -> Source | None:
        """None unless the source belongs to `project_id`. Removed sources are returned too."""
        ...

    def latest_version_of(self, source_id: SourceId) -> SourceVersion: ...

    def blocks(self, version_id: SourceVersionId) -> list[SourceBlock]: ...

    def version_text(self, version_id: SourceVersionId) -> str: ...

    def speaker_labels(self, version_id: SourceVersionId) -> list[SpeakerLabel] | None:
        """The stored labels in order of first appearance, or None if never looked for."""
        ...


class SpeakerStore(SpeakerReader, Protocol):
    def add_speaker_labels(
        self, version_id: SourceVersionId, labels: Sequence[SpeakerLabel], detected_at: datetime
    ) -> None: ...


@dataclass(frozen=True)
class SourceSpeakers:
    """The speaker labels in a source's current version; none unless it is a transcript."""

    source: Source
    version: SourceVersion
    speakers: list[SpeakerLabel]


def list_source_speakers(
    store: SpeakerStore, access: ProjectAccess, source_id: SourceId, now: datetime
) -> SourceSpeakers:
    """Any role on the project may read. A transcript stored before speakers were detected has
    its labels found and stored now, in the caller's transaction."""
    access.require_member()
    source = store.get_source(access.project_id, source_id)
    if source is None or source.kind is SourceKind.CHANGE_REQUEST:
        raise NotFoundError("Source not found")
    version = store.latest_version_of(source.id)
    labels, found_now = labels_of(store, version)
    if found_now:
        store.add_speaker_labels(version.id, labels, now)
    return SourceSpeakers(source=source, version=version, speakers=labels)


def labels_of(store: SpeakerReader, version: SourceVersion) -> tuple[list[SpeakerLabel], bool]:
    """A version's labels, and whether they were found now rather than read from storage.

    Detection is deterministic, so labels found now are the ones storing them would keep.
    """
    if version.kind is not SourceKind.TRANSCRIPT:
        return [], False
    stored = store.speaker_labels(version.id)
    if stored is not None:
        return stored, False
    text = store.version_text(version.id)
    return speaker_labels(version.id, text, store.blocks(version.id)), True
