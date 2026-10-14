from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.application import candidates, editing
from scopesteps.backlog.domain.candidate import (
    CandidateProposal,
    CandidateRejectedError,
    ProposedCriterion,
    ProposedDecision,
    ProposedItem,
)
from scopesteps.backlog.domain.editing import VersionChangedError, VersionNotDraftError
from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, DecisionId, ItemId
from scopesteps.backlog.domain.review import CheckCode, CheckResult
from scopesteps.backlog.domain.status import NO_VERSIONS, ScopeState, ScopeStatus, scope_status
from scopesteps.backlog.domain.version import (
    MAX_EPICS,
    MAX_STORIES,
    BlockerCode,
    ClaimOrigin,
    Evidence,
    ScopeNote,
    SuggestionStatus,
    VersionState,
)
from scopesteps.backlog.infrastructure.repository import SqlVersionRepository
from scopesteps.evidence.client import Citation, EvidenceRef, InvalidCitation, check_citations
from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectId


class Blocker(BaseModel):
    """A reason scope cannot be approved yet. `item_id` is null when no item is affected."""

    code: BlockerCode
    message: str
    item_id: ItemId | None
    decision_id: DecisionId | None = None
    criterion_id: CriterionId | None = None


class AcceptanceCriterion(BaseModel):
    id: CriterionId
    text: str = Field(min_length=1)
    origin: ClaimOrigin = Field(
        description="source: stated by the cited passages. human: confirmed by a reviewer's "
        "answer. proposed: an agent suggestion with no source. person: added by a person."
    )
    evidence: list[EvidenceRef] = []
    confirmed_by: list[DecisionId] = Field(
        default=[], description="The answered decisions that confirm a human-origin criterion."
    )
    suggestion: SuggestionStatus | None = Field(
        default=None,
        description="Set exactly for an agent suggestion (origin proposed): pending until an "
        "editor accepts or rejects it. Rejected suggestions are left out of an approved version.",
    )
    edited_by: UserId | None = Field(
        default=None, description="The person who last wrote the text, if a person did."
    )


class BacklogItem(BaseModel):
    """An epic or story. `id` is stable across versions; edits never reuse it for new work."""

    id: ItemId
    kind: Literal["epic", "story"]
    parent_id: ItemId | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    criteria: list[AcceptanceCriterion] = []
    assumptions: list[str] = []
    open_questions: list[str] = []
    blockers: list[Blocker] = []
    human_edited: bool = Field(
        default=False, description="A person changed the title, description or criteria."
    )
    edited_by: UserId | None = Field(default=None, description="Who last changed the item.")
    edited_at: datetime | None = None


def _citation_checker(session: Session) -> candidates.CitationChecker:
    def check(project_id: ProjectId, citations: Sequence[Citation]) -> list[InvalidCitation]:
        return check_citations(session, project_id, citations)

    return check


def candidate_problems(session: Session, proposal: CandidateProposal) -> list[str]:
    """Why `proposal` would be rejected; empty when `save_candidate` will accept it."""
    return candidates.candidate_problems(_citation_checker(session), proposal)


def save_candidate(
    session: Session, proposal: CandidateProposal, now: datetime
) -> BacklogVersionId:
    """Save a run's candidate as a draft version in the caller's transaction, at most once per run.

    Nothing here approves anything: the version stays a draft until a reviewer acts on it. A
    newly saved version is recorded in the activity log as the agent's action. Raises
    CandidateRejectedError, saving nothing, if the proposal fails validation.
    """
    version = candidates.save_candidate(
        SqlVersionRepository(session),
        audit_recorder(session),
        _citation_checker(session),
        proposal,
        now,
    )
    return version.id


def find_candidate(session: Session, run_id: UUID) -> BacklogVersionId | None:
    return SqlVersionRepository(session).find_id_by_run(run_id)


@dataclass(frozen=True)
class VersionSummary:
    """What a decision on a version needs to know about it, without its content."""

    id: BacklogVersionId
    project_id: ProjectId
    base_version_id: BacklogVersionId | None
    revision: int
    state: VersionState
    content_hash: str
    epics: int
    stories: int


def load_version_summary(session: Session, version_id: BacklogVersionId) -> VersionSummary | None:
    """Performs no access check: the caller resolves access to the returned project."""
    version = SqlVersionRepository(session).get(version_id)
    if version is None:
        return None
    epics = sum(1 for item in version.items if item.kind == "epic")
    return VersionSummary(
        id=version.id,
        project_id=version.project_id,
        base_version_id=version.base_version_id,
        revision=version.revision,
        state=version.state,
        content_hash=version.content_hash,
        epics=epics,
        stories=len(version.items) - epics,
    )


def approval_checks(session: Session, version_id: BacklogVersionId) -> tuple[CheckResult, ...]:
    """Every approval check on the version's stored content, run now."""
    version = SqlVersionRepository(session).get(version_id)
    if version is None:
        raise NotFoundError("Backlog version not found")
    return editing.run_checks(_citation_checker(session), version)


def freeze_approved(
    session: Session, version_id: BacklogVersionId, *, expected_revision: int, content_hash: str
) -> bool:
    """Make the draft an approved, unchangeable version in the caller's transaction, leaving out
    its rejected suggestions. False, changing nothing, if it is no longer a draft at exactly
    that revision and hash."""
    return SqlVersionRepository(session).freeze_approved(
        version_id, expected_revision=expected_revision, content_hash=content_hash
    )


def mark_rejected(
    session: Session, version_id: BacklogVersionId, *, expected_revision: int
) -> bool:
    """Mark the draft rejected in the caller's transaction. False, changing nothing, if it is no
    longer a draft at that revision."""
    return SqlVersionRepository(session).mark_rejected(
        version_id, expected_revision=expected_revision
    )


def load_scope_statuses(
    session: Session, project_ids: Collection[ProjectId]
) -> dict[ProjectId, ScopeStatus]:
    """Where each project's scope stands, for every id given, in one query.

    Performs no access check: callers pass only projects the actor may see.
    """
    headers = SqlVersionRepository(session).headers_by_project(project_ids)
    return {
        project_id: scope_status(headers[project_id]) if project_id in headers else NO_VERSIONS
        for project_id in project_ids
    }


__all__ = [
    "MAX_EPICS",
    "MAX_STORIES",
    "AcceptanceCriterion",
    "BacklogItem",
    "BacklogVersionId",
    "Blocker",
    "CandidateProposal",
    "CandidateRejectedError",
    "CheckCode",
    "CheckResult",
    "ClaimOrigin",
    "CriterionId",
    "DecisionId",
    "Evidence",
    "ItemId",
    "ProposedCriterion",
    "ProposedDecision",
    "ProposedItem",
    "ScopeNote",
    "ScopeState",
    "ScopeStatus",
    "SuggestionStatus",
    "VersionChangedError",
    "VersionNotDraftError",
    "VersionState",
    "VersionSummary",
    "approval_checks",
    "candidate_problems",
    "find_candidate",
    "freeze_approved",
    "load_scope_statuses",
    "load_version_summary",
    "mark_rejected",
    "save_candidate",
]
