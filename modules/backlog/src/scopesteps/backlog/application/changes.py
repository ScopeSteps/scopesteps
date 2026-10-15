"""Saving a change run's proposal as a candidate in review, built from the current baseline.

Like a draft candidate, it is checked twice: the agent checks the model's change set against the
labels it showed the model, and this module checks the result against what is stored.
"""

from collections.abc import Callable
from datetime import datetime

from scopesteps.backlog.application.candidates import CitationChecker, VersionStore
from scopesteps.backlog.domain.change import (
    BuiltChange,
    ChangeProposal,
    ChangeRejectedError,
    build_change_candidate,
    change_problems,
)
from scopesteps.backlog.domain.ids import BacklogVersionId
from scopesteps.evidence.client import Citation
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

BaselineFinder = Callable[[ProjectId], BacklogVersionId | None]
"""The project's current baseline: its newest approved version."""


def change_candidate_problems(
    store: VersionStore,
    current_baseline: BaselineFinder,
    check_citations: CitationChecker,
    proposal: ChangeProposal,
) -> list[str]:
    """Everything that makes the proposal unsafe to save; empty when it may be saved."""
    base = store.get(proposal.base_version_id)
    if base is None or base.project_id != proposal.project_id:
        return ["the change is not based on a version of this project"]
    if current_baseline(proposal.project_id) != base.id:
        return [f"version {base.id} is no longer the project's baseline"]
    problems = change_problems(base, proposal)
    evidence = proposal.evidence()
    pinned = {str(v) for v in proposal.source_version_ids}
    unpinned = sorted({str(e.source_version_id) for e in evidence} - pinned)
    problems += [f"evidence cites source version {v}, which the run did not pin" for v in unpinned]
    citations = list(
        dict.fromkeys(Citation(e.source_version_id, e.block_id, e.quote) for e in evidence)
    )
    problems += [invalid.message for invalid in check_citations(proposal.project_id, citations)]
    return problems


def save_change_candidate(
    store: VersionStore,
    current_baseline: BaselineFinder,
    check_citations: CitationChecker,
    proposal: ChangeProposal,
    now: datetime,
) -> BuiltChange:
    """Save the change as a candidate in review, once per run. Raises ChangeRejectedError, saving
    nothing, if the proposal fails or the run already has a candidate. The baseline is only
    read; the caller records the action."""
    if store.find_by_run(proposal.run_id) is not None:
        raise ChangeRejectedError(["this run already proposed a candidate"])
    problems = change_candidate_problems(store, current_baseline, check_citations, proposal)
    base = store.get(proposal.base_version_id)
    if problems or base is None:
        raise ChangeRejectedError(problems or ["the baseline was not found"])
    built = build_change_candidate(base, proposal, new_id=new_id, now=now)
    store.add(built.version)
    return built
