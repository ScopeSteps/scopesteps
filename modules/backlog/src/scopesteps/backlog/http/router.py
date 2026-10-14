from collections.abc import Sequence
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.application import candidates, editing, history
from scopesteps.backlog.client import (
    AcceptanceCriterion,
    BacklogItem,
    BacklogVersionId,
    Blocker,
    DecisionId,
    DecisionReader,
    ItemId,
    get_decision_reader,
    load_scope_statuses,
)
from scopesteps.backlog.domain import version as domain
from scopesteps.backlog.domain.editing import CriterionEdit, ItemEdit, VersionChangedError
from scopesteps.backlog.http.schemas import (
    BacklogDecision,
    BacklogVersionPage,
    BacklogVersionResponse,
    BacklogVersionSummary,
    CheckResponse,
    CriterionChangeResponse,
    DecisionAnswerRequest,
    ItemChangeResponse,
    ItemPatchRequest,
    ReviewRequest,
    ReviewResponse,
    ScopeNoteResponse,
    VersionComparisonResponse,
    VersionDecisionResponse,
)
from scopesteps.backlog.infrastructure.repository import SqlReceiptStore, SqlVersionRepository
from scopesteps.evidence.client import EvidenceRef, check_citations
from scopesteps.identity.client import (
    ProjectAccess,
    ProjectAccessResolver,
    get_project_access,
    get_project_access_resolver,
)
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import IdempotencyKey, SessionDep
from scopesteps.kernel.errors import FeatureNotImplementedError
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceBlockId, SourceVersionId

router = APIRouter(tags=["backlog"])

ResolverDep = Annotated[ProjectAccessResolver, Depends(get_project_access_resolver)]


@router.get("/projects/{project_id}/backlogs")
def list_backlog_versions(
    project_id: ProjectId,
    access: Annotated[ProjectAccess, Depends(get_project_access)],
    decisions: Annotated[DecisionReader, Depends(get_decision_reader)],
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=history.MAX_PAGE_SIZE)] = history.DEFAULT_PAGE_SIZE,
    cursor: Annotated[
        str | None,
        Query(max_length=200, description="`next_cursor` of the previous page."),
    ] = None,
) -> BacklogVersionPage:
    """The project's versions, newest first, each with how it was decided. Any member may read
    it; it changes nothing."""
    page = history.list_versions(
        SqlVersionRepository(session), decisions, access, limit=limit, cursor=cursor
    )
    return BacklogVersionPage(
        versions=[
            BacklogVersionSummary(
                id=listed.version.id,
                number=None if listed.decision is None else listed.decision.baseline_number,
                state=listed.version.state.value,
                revision=listed.version.revision,
                content_hash=listed.version.content_hash,
                base_version_id=listed.version.base_version_id,
                run_id=listed.version.run_id,
                created_by=listed.version.created_by,
                created_at=listed.version.created_at,
                decision=None
                if listed.decision is None
                else VersionDecisionResponse(
                    decision=listed.decision.decision,
                    decided_by=listed.decision.decided_by,
                    decided_at=listed.decision.decided_at,
                ),
            )
            for listed in page.versions
        ],
        next_cursor=page.next_cursor,
    )


# Declared before the route for one version, which would otherwise take "compare" as its id.
@router.get("/projects/{project_id}/backlogs/compare")
def compare_backlog_versions(
    project_id: ProjectId,
    access: Annotated[ProjectAccess, Depends(get_project_access)],
    session: SessionDep,
    base: Annotated[BacklogVersionId, Query(description="The version to compare from.")],
    candidate: Annotated[BacklogVersionId, Query(description="The version to compare to.")],
) -> VersionComparisonResponse:
    """What changes from `base` to `candidate`, any two versions of the project, matched by
    stable item and criterion ids. Any member may compare; it changes nothing."""
    comparison = history.compare_versions(SqlVersionRepository(session), access, base, candidate)
    return VersionComparisonResponse(
        base_version_id=comparison.base.id,
        base_content_hash=comparison.base.content_hash,
        candidate_version_id=comparison.candidate.id,
        candidate_content_hash=comparison.candidate.content_hash,
        operations=[
            ItemChangeResponse(
                kind=change.kind,
                item_id=change.item_id,
                before=None if change.before is None else _item(change.before, comparison.base),
                after=None if change.after is None else _item(change.after, comparison.candidate),
                changed_fields=list(change.changed_fields),
                criteria=[
                    CriterionChangeResponse(
                        kind=criterion.kind,
                        criterion_id=criterion.criterion_id,
                        before=None if criterion.before is None else _criterion(criterion.before),
                        after=None if criterion.after is None else _criterion(criterion.after),
                    )
                    for criterion in change.criteria
                ],
            )
            for change in comparison.changes
        ],
    )


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
    resolve: ResolverDep,
    session: SessionDep,
) -> BacklogVersionResponse:
    """Edit one item of a draft, accept or reject its agent suggestions, or add criteria. Needs
    the editor role.

    409 `VERSION_CHANGED` means `expected_revision` is stale: reload the version.
    409 `VERSION_NOT_DRAFT` means the version is approved or rejected and never changes.
    """
    edit = ItemEdit(
        title=body.title,
        description=body.description,
        criteria=None
        if body.criteria is None
        else tuple(CriterionEdit(c.id, c.text, c.suggestion) for c in body.criteria),
    )
    try:
        version = editing.edit_item(
            SqlVersionRepository(session),
            SqlReceiptStore(session),
            audit_recorder(session),
            resolve,
            version_id,
            editing.EditItem(
                idempotency_key=idempotency_key,
                item_id=item_id,
                expected_revision=body.expected_revision,
                edit=edit,
            ),
            utc_now(),
        )
        session.commit()
    except IntegrityError as error:
        # A concurrent request with the same Idempotency-Key won. Nothing of this one was stored.
        session.rollback()
        raise VersionChangedError(
            "Another request finished first. Reload the backlog and try again."
        ) from error
    return _response(version)


@router.patch("/backlogs/{version_id}/decisions/{decision_id}")
def answer_backlog_decision(
    version_id: BacklogVersionId,
    decision_id: DecisionId,
    body: DecisionAnswerRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    session: SessionDep,
) -> BacklogVersionResponse:
    """Settle an open or skipped decision on a draft with a reviewer's answer. Needs the editor
    or approver role. This is how a decision skipped during the run is resolved before approval.

    409 `DECISION_ALREADY_ANSWERED` means it was settled already; the answer stays as it was.
    409 `VERSION_CHANGED` means `expected_revision` is stale: reload the version.
    409 `VERSION_NOT_DRAFT` means the version is approved or rejected and never changes.
    """
    try:
        version = editing.answer_open_decision(
            SqlVersionRepository(session),
            SqlReceiptStore(session),
            audit_recorder(session),
            resolve,
            version_id,
            editing.AnswerDecision(
                idempotency_key=idempotency_key,
                decision_id=decision_id,
                expected_revision=body.expected_revision,
                answer=body.answer,
            ),
            utc_now(),
        )
        session.commit()
    except IntegrityError as error:
        # A concurrent request with the same Idempotency-Key won. Nothing of this one was stored.
        session.rollback()
        raise VersionChangedError(
            "Another request finished first. Reload the backlog and try again."
        ) from error
    return _response(version)


@router.post("/backlogs/{version_id}/review")
def review_backlog(
    version_id: BacklogVersionId,
    body: ReviewRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    session: SessionDep,
) -> ReviewResponse:
    """Run every approval check on the version at `expected_revision`, for any member.

    Changes nothing, so repeating it is always safe; the Idempotency-Key is accepted like on
    every command. Approval runs the same checks again.
    """
    review = editing.review_version(
        SqlVersionRepository(session),
        _citation_checker(session),
        resolve,
        version_id,
        body.expected_revision,
    )
    version = review.version
    baseline = load_scope_statuses(session, [version.project_id])[version.project_id]
    epics = sum(1 for item in version.items if item.kind == "epic")
    return ReviewResponse(
        version_id=version.id,
        revision=version.revision,
        state=version.state.value,
        content_hash=version.content_hash,
        base_version_id=version.base_version_id,
        baseline_version_id=baseline.baseline_version_id,
        epic_count=epics,
        story_count=len(version.items) - epics,
        ready=review.ready,
        checks=[
            CheckResponse(
                code=check.code,
                title=check.title,
                passed=check.passed,
                problems=list(check.problems),
                problem_count=check.problem_count,
            )
            for check in review.checks
        ],
        blockers=[_blocker(blocker) for blocker in version.blockers()],
    )


def _citation_checker(session: Session) -> candidates.CitationChecker:
    return lambda project_id, citations: check_citations(session, project_id, citations)


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
        items=[_item(item, version, blockers) for item in version.items],
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


def _criterion(criterion: domain.Criterion) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        id=criterion.id,
        text=criterion.text,
        origin=criterion.origin,
        evidence=_evidence(criterion.evidence),
        confirmed_by=list(criterion.confirmed_by),
        suggestion=criterion.suggestion,
        edited_by=criterion.edited_by,
    )


def _item(
    item: domain.Item, version: domain.BacklogVersion, blockers: Sequence[Blocker] | None = None
) -> BacklogItem:
    all_blockers = blockers if blockers is not None else [_blocker(b) for b in version.blockers()]
    return BacklogItem(
        id=item.id,
        kind=item.kind,
        parent_id=item.parent_id,
        title=item.title,
        description=item.description,
        criteria=[_criterion(criterion) for criterion in item.criteria],
        assumptions=list(item.assumptions),
        open_questions=list(item.open_questions),
        blockers=[blocker for blocker in all_blockers if blocker.item_id == item.id],
        human_edited=item.human_edited,
        edited_by=item.edited_by,
        edited_at=item.edited_at,
    )
