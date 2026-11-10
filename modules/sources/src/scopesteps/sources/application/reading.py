from collections.abc import Sequence
from typing import Protocol

from scopesteps.identity.client import ProjectAccess
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectId
from scopesteps.sources.domain.ids import SourceId, SourceVersionId
from scopesteps.sources.domain.source import Source, SourceBlock, SourceVersion


class SourceReader(Protocol):
    def current_versions(self, project_id: ProjectId) -> list[SourceVersion]:
        """The latest version of each source the project has not removed, by source number."""
        ...

    def get_version(
        self, project_id: ProjectId, version_id: SourceVersionId
    ) -> SourceVersion | None:
        """None unless the version belongs to `project_id`."""
        ...

    def blocks(self, version_id: SourceVersionId) -> list[SourceBlock]: ...


def list_current_sources(store: SourceReader, access: ProjectAccess) -> list[SourceVersion]:
    access.require_member()
    return store.current_versions(access.project_id)


class SourceHistoryReader(Protocol):
    def get_source(self, project_id: ProjectId, source_id: SourceId) -> Source | None:
        """None unless the source belongs to `project_id`."""
        ...

    def versions_of(self, source_id: SourceId) -> list[SourceVersion]:
        """Every version of the source, newest first."""
        ...


def list_source_versions(
    store: SourceHistoryReader, access: ProjectAccess, source_id: SourceId
) -> list[SourceVersion]:
    """A current source's versions, newest first, so earlier ones can still be read. A removed
    source is not listed, as it is not among the current sources."""
    access.require_member()
    source = store.get_source(access.project_id, source_id)
    if source is None or source.is_removed:
        raise NotFoundError("Source not found")
    return store.versions_of(source_id)


def list_source_blocks(
    store: SourceReader, access: ProjectAccess, version_id: SourceVersionId
) -> list[SourceBlock]:
    return read_source_version(store, access, version_id)[1]


def read_source_version(
    store: SourceReader, access: ProjectAccess, version_id: SourceVersionId
) -> tuple[SourceVersion, list[SourceBlock]]:
    """A version of any kind, change requests included, with its paragraphs."""
    access.require_member()
    version = store.get_version(access.project_id, version_id)
    if version is None:
        raise NotFoundError("Source version not found")
    return version, store.blocks(version_id)


def versions_with_blocks(
    store: SourceReader, project_id: ProjectId, version_ids: Sequence[SourceVersionId]
) -> list[tuple[SourceVersion, list[SourceBlock]]]:
    """Each version with its paragraphs, in the order given. Every version must be in `project_id`."""
    found: list[tuple[SourceVersion, list[SourceBlock]]] = []
    for version_id in version_ids:
        version = store.get_version(project_id, version_id)
        if version is None:
            raise NotFoundError("Source version not found")
        found.append((version, store.blocks(version_id)))
    return found
