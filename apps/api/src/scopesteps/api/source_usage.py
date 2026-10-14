"""Binds `sources.client.get_source_usage_reader` to the modules that refer to source versions."""

from collections.abc import Collection

from scopesteps.agent.client import runs_pinning_sources
from scopesteps.backlog.client import versions_citing_sources
from scopesteps.infrastructure.http import SessionDep
from scopesteps.projects.client import ProjectId
from scopesteps.projects.http.dependencies import people_citing_sources
from scopesteps.sources.client import SourceUsageReader, SourceUse, SourceVersionId


def resolve_source_usage_reader(session: SessionDep) -> SourceUsageReader:
    def read(project_id: ProjectId, version_ids: Collection[SourceVersionId]) -> list[SourceUse]:
        return [
            *(SourceUse("run", i) for i in runs_pinning_sources(session, project_id, version_ids)),
            *(
                SourceUse("backlog_version", i)
                for i in versions_citing_sources(session, project_id, version_ids)
            ),
            *(
                SourceUse("person", i)
                for i in people_citing_sources(session, project_id, version_ids)
            ),
        ]

    return read
