"""Exporting an approved version for any member of its project."""

from datetime import datetime

from scopesteps.backlog.application.candidates import CitationChecker, VersionStore
from scopesteps.backlog.domain.export import ApprovedSnapshot, approved_snapshot, require_approved
from scopesteps.backlog.domain.ids import BacklogVersionId
from scopesteps.backlog.domain.review import cited_evidence
from scopesteps.backlog.domain.version import Evidence
from scopesteps.backlog.domain.version_decision import DecisionReader
from scopesteps.evidence.client import Citation
from scopesteps.identity.client import ProjectAccessResolver
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectReader


def export_version(
    store: VersionStore,
    resolve: ProjectAccessResolver,
    decisions: DecisionReader,
    read_project: ProjectReader,
    check_citations: CitationChecker,
    version_id: BacklogVersionId,
    now: datetime,
) -> ApprovedSnapshot:
    """The stored approved version, never the latest one or a draft.

    Every citation is checked again against the project's stored passages, so evidence that no
    longer resolves is left out and counted rather than exported.
    """
    version = store.get(version_id)
    if version is None:
        raise NotFoundError("Backlog version not found")
    # Membership is checked before the state, so a non-member learns nothing about the version.
    if not resolve(version.project_id).roles:
        raise NotFoundError("Backlog version not found")
    approval = require_approved(version, decisions([version.id]).get(version.id))
    evidence = cited_evidence(version)
    citations = [Citation(e.source_version_id, e.block_id, e.quote) for e in evidence]
    invalid = {
        fault.citation
        for fault in (check_citations(version.project_id, citations) if citations else [])
    }

    def permitted(e: Evidence) -> bool:
        return Citation(e.source_version_id, e.block_id, e.quote) not in invalid

    project = read_project(version.project_id)
    return approved_snapshot(
        version,
        approval,
        project_name="Project" if project is None else project.name,
        exported_at=now,
        permitted=permitted,
    )
