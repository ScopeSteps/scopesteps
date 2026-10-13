"""Saving an agent run's candidate and reading versions back.

A candidate is checked twice on purpose: the agent checks the draft the model wrote against the
passages it showed the model, and this module checks the mapped result against what is stored,
so a mistake between the two cannot put an unverifiable reference into a version.
"""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.backlog.domain.candidate import (
    CandidateProposal,
    CandidateRejectedError,
    build_candidate,
    structural_problems,
)
from scopesteps.backlog.domain.ids import BacklogVersionId
from scopesteps.backlog.domain.version import BacklogVersion
from scopesteps.evidence.client import Citation, InvalidCitation
from scopesteps.identity.client import ProjectAccess
from scopesteps.kernel.errors import NotFoundError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId


class VersionStore(Protocol):
    def get(self, version_id: BacklogVersionId) -> BacklogVersion | None: ...

    def find_by_run(self, run_id: UUID) -> BacklogVersion | None: ...

    def add(self, version: BacklogVersion) -> None:
        """Insert within the caller's transaction; the caller commits."""
        ...


CitationChecker = Callable[[ProjectId, Sequence[Citation]], list[InvalidCitation]]
"""Returns the citations that do not resolve to a stored passage of the project."""


def candidate_problems(check_citations: CitationChecker, proposal: CandidateProposal) -> list[str]:
    """Everything that makes a proposal unsafe to save; empty when it may be saved."""
    problems = structural_problems(proposal)
    evidence = proposal.evidence()
    unpinned = sorted(
        {str(e.source_version_id) for e in evidence} - {str(v) for v in proposal.source_version_ids}
    )
    problems += [f"evidence cites source version {v}, which the run did not pin" for v in unpinned]
    citations = list(
        dict.fromkeys(Citation(e.source_version_id, e.block_id, e.quote) for e in evidence)
    )
    problems += [invalid.message for invalid in check_citations(proposal.project_id, citations)]
    return problems


def save_candidate(
    store: VersionStore,
    check_citations: CitationChecker,
    proposal: CandidateProposal,
    now: datetime,
) -> BacklogVersion:
    """Save the run's candidate as a draft version, once: a run that already has a candidate
    gets that one back. Raises CandidateRejectedError, saving nothing, if the proposal fails."""
    existing = store.find_by_run(proposal.run_id)
    if existing is not None:
        return existing
    problems = candidate_problems(check_citations, proposal)
    if problems:
        raise CandidateRejectedError(problems)
    version = build_candidate(proposal, new_id=new_id, now=now)
    store.add(version)
    return version


def get_version(
    store: VersionStore, access: ProjectAccess, version_id: BacklogVersionId
) -> BacklogVersion:
    access.require_member()
    version = store.get(version_id)
    # A version of another project is reported exactly like a missing one.
    if version is None or version.project_id != access.project_id:
        raise NotFoundError("Backlog version not found")
    return version
