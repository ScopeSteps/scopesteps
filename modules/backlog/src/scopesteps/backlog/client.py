from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.application import candidates
from scopesteps.backlog.domain.candidate import (
    CandidateProposal,
    CandidateRejectedError,
    ProposedCriterion,
    ProposedDecision,
    ProposedItem,
)
from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, DecisionId, ItemId
from scopesteps.backlog.domain.status import NO_VERSIONS, ScopeState, ScopeStatus, scope_status
from scopesteps.backlog.domain.version import (
    MAX_EPICS,
    MAX_STORIES,
    BlockerCode,
    ClaimOrigin,
    Evidence,
    ScopeNote,
)
from scopesteps.backlog.infrastructure.repository import SqlVersionRepository
from scopesteps.evidence.client import Citation, EvidenceRef, InvalidCitation, check_citations
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
        "answer. proposed: added by the AI and not yet reviewed."
    )
    evidence: list[EvidenceRef] = []
    confirmed_by: list[DecisionId] = Field(
        default=[], description="The answered decisions that confirm a human-origin criterion."
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
    human_edited: bool = False


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
    "candidate_problems",
    "find_candidate",
    "load_scope_statuses",
    "save_candidate",
]
