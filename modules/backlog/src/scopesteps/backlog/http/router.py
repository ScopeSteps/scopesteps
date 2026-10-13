from collections.abc import Sequence
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from scopesteps.backlog.application import candidates
from scopesteps.backlog.client import (
    AcceptanceCriterion,
    BacklogItem,
    BacklogVersionId,
    Blocker,
    ItemId,
)
from scopesteps.backlog.domain import version as domain
from scopesteps.backlog.http.schemas import (
    BacklogDecision,
    BacklogVersionResponse,
    ItemPatchRequest,
    ReviewRequest,
    ReviewResponse,
    ScopeNoteResponse,
)
from scopesteps.backlog.infrastructure.repository import SqlVersionRepository
from scopesteps.evidence.client import EvidenceRef
from scopesteps.identity.client import ProjectAccess, get_project_access
from scopesteps.infrastructure.http import IdempotencyKey, SessionDep
from scopesteps.kernel.errors import FeatureNotImplementedError
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceBlockId, SourceVersionId

router = APIRouter(tags=["backlog"])


@router.get("/projects/{project_id}/backlogs/{version_id}")
def get_backlog_version(
    project_id: ProjectId,
    version_id: BacklogVersionId,
    access: Annotated[ProjectAccess, Depends(get_project_access)],
    session: SessionDep,
) -> BacklogVersionResponse:
    """A draft or approved version with its evidence, decisions and blockers."""
    version = candidates.get_version(SqlVersionRepository(session), access, version_id)
    return _response(version)


@router.patch("/backlogs/{version_id}/items/{item_id}")
def update_backlog_item(
    version_id: BacklogVersionId,
    item_id: ItemId,
    body: ItemPatchRequest,
    idempotency_key: IdempotencyKey,
) -> BacklogVersionResponse:
    raise FeatureNotImplementedError("Backlog item editing")


@router.post("/backlogs/{version_id}/review")
def submit_for_review(
    version_id: BacklogVersionId, body: ReviewRequest, idempotency_key: IdempotencyKey
) -> ReviewResponse:
    raise FeatureNotImplementedError("Backlog review")


@router.get(
    "/backlogs/{version_id}/export",
    responses={200: {"content": {"text/markdown": {"schema": {"type": "string"}}}}},
)
def export_backlog(
    version_id: BacklogVersionId,
    export_format: Annotated[Literal["json", "markdown"], Query(alias="format")] = "json",
) -> BacklogVersionResponse:
    raise FeatureNotImplementedError("Backlog export")


def _evidence(evidence: Sequence[domain.Evidence]) -> list[EvidenceRef]:
    return [
        EvidenceRef(
            source_version_id=SourceVersionId(e.source_version_id),
            block_id=SourceBlockId(e.block_id),
            quote=e.quote,
            relationship=e.relationship,
        )
        for e in evidence
    ]


def _blocker(blocker: domain.Blocker) -> Blocker:
    return Blocker(
        code=blocker.code,
        message=blocker.message,
        item_id=blocker.item_id,
        decision_id=blocker.decision_id,
        criterion_id=blocker.criterion_id,
    )


def _response(version: domain.BacklogVersion) -> BacklogVersionResponse:
    blockers = [_blocker(blocker) for blocker in version.blockers()]
    return BacklogVersionResponse(
        id=version.id,
        project_id=version.project_id,
        base_version_id=version.base_version_id,
        revision=version.revision,
        state=version.state.value,
        content_hash=version.content_hash,
        run_id=version.run_id,
        source_version_ids=[SourceVersionId(v) for v in version.source_version_ids],
        items=[
            BacklogItem(
                id=item.id,
                kind=item.kind,
                parent_id=item.parent_id,
                title=item.title,
                description=item.description,
                criteria=[
                    AcceptanceCriterion(
                        id=criterion.id,
                        text=criterion.text,
                        origin=criterion.origin,
                        evidence=_evidence(criterion.evidence),
                        confirmed_by=list(criterion.confirmed_by),
                    )
                    for criterion in item.criteria
                ],
                assumptions=list(item.assumptions),
                open_questions=list(item.open_questions),
                blockers=[blocker for blocker in blockers if blocker.item_id == item.id],
                human_edited=item.human_edited,
            )
            for item in version.items
        ],
        decisions=[
            BacklogDecision(
                id=decision.id,
                kind=decision.kind,
                status=decision.status,
                subject=decision.subject,
                question=decision.question,
                why_it_matters=decision.why_it_matters,
                evidence=_evidence(decision.evidence),
                affected_item_ids=list(decision.affected_item_ids),
                question_id=decision.question_id,
                answer=decision.answer,
                decided_by=decision.decided_by,
                decided_at=decision.decided_at,
            )
            for decision in version.decisions
        ],
        out_of_scope=[
            ScopeNoteResponse(
                kind=note.kind, summary=note.summary, evidence=_evidence(note.evidence)
            )
            for note in version.out_of_scope
        ],
        blockers=blockers,
        created_at=version.created_at,
    )
