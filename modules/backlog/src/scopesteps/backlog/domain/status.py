"""Where a project's scope stands, derived from its versions every time it is read."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from scopesteps.backlog.domain.ids import BacklogVersionId
from scopesteps.backlog.domain.version import VersionState


class ScopeState(StrEnum):
    NO_BASELINE = "no_baseline"
    DRAFT_IN_PROGRESS = "draft_in_progress"
    CANDIDATE_IN_REVIEW = "candidate_in_review"
    BASELINE = "baseline"


@dataclass(frozen=True)
class VersionHeader:
    id: BacklogVersionId
    state: VersionState
    created_at: datetime


@dataclass(frozen=True)
class ScopeStatus:
    """`state` names the work in flight if there is any, otherwise whether a baseline exists.

    The baseline fields are set whenever a version has been approved, whatever the state, so a
    project with a change in review still reports the baseline that change is measured against.
    """

    state: ScopeState
    baseline_version: int | None = None
    """1 for the first approved version, 2 for the second, and so on."""
    baseline_version_id: BacklogVersionId | None = None
    open_version_id: BacklogVersionId | None = None
    """The newest candidate in review, or else the newest draft, that `state` refers to."""


NO_VERSIONS = ScopeStatus(ScopeState.NO_BASELINE)


def scope_status(versions: Sequence[VersionHeader]) -> ScopeStatus:
    """A draft or candidate counts as in flight only if it is newer than the current baseline:
    older ones were overtaken by that approval. Rejected versions never count."""
    # UUIDv7 ids break ties between versions created in the same instant.
    ordered = sorted(versions, key=lambda version: (version.created_at, version.id))
    approved = [version for version in ordered if version.state is VersionState.APPROVED]
    baseline = approved[-1] if approved else None
    in_flight = ordered if baseline is None else ordered[ordered.index(baseline) + 1 :]

    def newest(state: VersionState) -> VersionHeader | None:
        return next((v for v in reversed(in_flight) if v.state is state), None)

    candidate = newest(VersionState.IN_REVIEW)
    draft = newest(VersionState.DRAFT)
    if candidate is not None:
        state, open_version = ScopeState.CANDIDATE_IN_REVIEW, candidate
    elif draft is not None:
        state, open_version = ScopeState.DRAFT_IN_PROGRESS, draft
    elif baseline is not None:
        state, open_version = ScopeState.BASELINE, None
    else:
        state, open_version = ScopeState.NO_BASELINE, None
    return ScopeStatus(
        state=state,
        baseline_version=len(approved) or None,
        baseline_version_id=None if baseline is None else baseline.id,
        open_version_id=None if open_version is None else open_version.id,
    )
