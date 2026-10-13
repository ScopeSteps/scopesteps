from typing import Protocol

from scopesteps.identity.client import ProjectAccess
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceVersionId
from scopesteps.sources.domain.source import SourceBlock, SourceVersion


class SourceReader(Protocol):
    def current_versions(self, project_id: ProjectId) -> list[SourceVersion]:
        """The latest version of each of the project's sources."""
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


def list_source_blocks(
    store: SourceReader, access: ProjectAccess, version_id: SourceVersionId
) -> list[SourceBlock]:
    access.require_member()
    if store.get_version(access.project_id, version_id) is None:
        raise NotFoundError("Source version not found")
    return store.blocks(version_id)
