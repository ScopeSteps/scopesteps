from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.application import candidates, editing, exporting, history
from scopesteps.backlog.client import (
    BacklogVersionId,
    CriterionId,
    DecisionId,
    DecisionReader,
    ItemId,
    blocker_response,
    evidence_refs,
    get_decision_reader,
    item_change_responses,
    item_response,
    load_scope_statuses,
)
from scopesteps.backlog.domain import version as domain
from scopesteps.backlog.domain.editing import CriterionEdit, ItemEdit, VersionChangedError
from scopesteps.backlog.domain.export import ApprovedSnapshot, export_filename, to_jira_csv
from scopesteps.backlog.http.schemas import (
    BacklogDecision,
    BacklogExport,
    BacklogVersionPage,
    BacklogVersionResponse,
    BacklogVersionSummary,
    CandidateSuggestionRequest,
    CheckResponse,
    DecisionAnswerRequest,
    ExportedCriterion,
    ExportedDecision,
    ExportedItem,
    ExportedProject,
    ExportedVersion,
    ItemPatchRequest,
    ProblemRefResponse,
    ReviewRequest,
    ReviewResponse,
    ScopeDecisionRequest,
    ScopeNoteResponse,
    SetAsideNoteResponse,
    VersionComparisonResponse,
    VersionDecisionResponse,
)
from scopesteps.backlog.infrastructure.repository import SqlReceiptStore, SqlVersionRepository
from scopesteps.evidence.client import check_citations
from scopesteps.identity.client import (
    ProjectAccess,
    ProjectAccessResolver,
    get_project_access,
    get_project_access_resolver,
)
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import IdempotencyKey, SessionDep
from scopesteps.projects.client import ProjectId, ProjectReader, get_project_reader
from scopesteps.sources.client import SourceVersionId

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
        operations=item_change_responses(comparison.base, comparison.candidate, comparison.changes),
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


@router.post("/backlogs/{version_id}/scope-decisions/{decision_id}")
def record_scope_decision(
    version_id: BacklogVersionId,
    decision_id: DecisionId,
    body: ScopeDecisionRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    session: SessionDep,
) -> BacklogVersionResponse:
    """Record an approver's reverse or keep on a required scope decision of a change candidate
    in review. Needs the approver role. Returns the candidate at its next revision.

    409 `DECISION_ALREADY_ANSWERED` means it was recorded already; it stays as it was.
    409 `NOT_A_SCOPE_DECISION` means the decision is not a scope reversal.
    409 `VERSION_NOT_IN_REVIEW` means the version is not a change candidate in review.
    409 `VERSION_CHANGED` means `expected_revision` is stale: reload the version.
    """
    try:
        version = editing.record_scope_decision(
            SqlVersionRepository(session),
            SqlReceiptStore(session),
            audit_recorder(session),
            resolve,
            version_id,
            editing.RecordScopeDecision(
                idempotency_key=idempotency_key,
                decision_id=decision_id,
                expected_revision=body.expected_revision,
                outcome=body.outcome,
            ),
            utc_now(),
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise VersionChangedError(
            "Another request finished first. Reload the backlog and try again."
        ) from error
    return _response(version)


@router.post("/backlogs/{version_id}/candidate-decisions/{decision_id}")
def answer_candidate_decision(
    version_id: BacklogVersionId,
    decision_id: DecisionId,
    body: DecisionAnswerRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    session: SessionDep,
) -> BacklogVersionResponse:
    """Settle an open or skipped decision of a change candidate in review, such as a
    clarification skipped during the change run, with an approver's answer. To close one that
    no longer applies, answer with why. Needs the approver role. Returns the candidate at its
    next revision, so it can then be approved.

    409 `DECISION_ALREADY_ANSWERED` means it was settled already; the answer stays as it was.
    409 `SCOPE_DECISION_NEEDS_OUTCOME` means it is a scope decision: use `scope-decisions`.
    409 `VERSION_NOT_IN_REVIEW` means the version is not a change candidate in review.
    409 `VERSION_CHANGED` means `expected_revision` is stale: reload the version.
    """
    try:
        version = editing.answer_candidate_open_decision(
            SqlVersionRepository(session),
            SqlReceiptStore(session),
            audit_recorder(session),
            resolve,
            version_id,
            editing.AnswerCandidateDecision(
                idempotency_key=idempotency_key,
                decision_id=decision_id,
                expected_revision=body.expected_revision,
                answer=body.answer,
            ),
            utc_now(),
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise VersionChangedError(
            "Another request finished first. Reload the backlog and try again."
        ) from error
    return _response(version)


@router.post("/backlogs/{version_id}/candidate-suggestions/{criterion_id}")
def review_candidate_suggestion(
    version_id: BacklogVersionId,
    criterion_id: CriterionId,
    body: CandidateSuggestionRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    session: SessionDep,
) -> BacklogVersionResponse:
    """Accept or reject an agent suggestion (a proposed criterion) of a change candidate in
    review. Needs the approver role. Returns the candidate at its next revision, so it can then
    be approved.

    409 `SUGGESTION_ALREADY_REVIEWED` means it was accepted or rejected already.
    409 `NOT_A_SUGGESTION` means the criterion is not an agent suggestion.
    409 `VERSION_NOT_IN_REVIEW` means the version is not a change candidate in review.
    409 `VERSION_CHANGED` means `expected_revision` is stale: reload the version.
    """
    try:
        version = editing.review_suggestion_on_candidate(
            SqlVersionRepository(session),
            SqlReceiptStore(session),
            audit_recorder(session),
            resolve,
            version_id,
            editing.ReviewCandidateSuggestion(
                idempotency_key=idempotency_key,
                criterion_id=criterion_id,
                expected_revision=body.expected_revision,
                outcome=body.outcome,
            ),
            utc_now(),
        )
        session.commit()
    except IntegrityError as error:
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
                refs=[
                    ProblemRefResponse(
                        item_id=ref.item_id,
                        criterion_id=ref.criterion_id,
                        decision_id=ref.decision_id,
                    )
                    for ref in check.refs
                ],
            )
            for check in review.checks
        ],
        blockers=[blocker_response(blocker) for blocker in version.blockers()],
    )


def _citation_checker(session: Session) -> candidates.CitationChecker:
    return lambda project_id, citations: check_citations(session, project_id, citations)


ExportFormat = Literal["csv", "json"]

# RFC 4180's registered type; `header=present` tells a reader the first row names the columns.
CSV_MEDIA_TYPE = "text/csv; charset=utf-8; header=present"


@router.get(
    "/backlogs/{version_id}/export",
    response_model=BacklogExport,
    responses={
        200: {
            "description": (
                "The approved version as an attachment: the complete version as JSON, or its "
                "epics and stories as CSV for Jira's importer."
            ),
            "content": {"text/csv": {"schema": {"type": "string"}}},
        }
    },
)
def export_backlog(
    version_id: BacklogVersionId,
    resolve: ResolverDep,
    decisions: Annotated[DecisionReader, Depends(get_decision_reader)],
    read_project: Annotated[ProjectReader, Depends(get_project_reader)],
    session: SessionDep,
    export_format: Annotated[ExportFormat, Query(alias="format")] = "json",
) -> Response:
    """Download an approved version as JSON or as a Jira CSV, for any member of its project.

    Exports the version exactly as it was approved, never a later baseline or a draft. JSON is
    the complete, lossless export and the default; CSV holds only what a Jira issue needs.
    409 `VERSION_NOT_APPROVED` means the version is a draft or was rejected.
    """
    snapshot = exporting.export_version(
        SqlVersionRepository(session),
        resolve,
        decisions,
        read_project,
        _citation_checker(session),
        version_id,
        utc_now(),
    )
    if export_format == "csv":
        body, media_type, extension = to_jira_csv(snapshot), CSV_MEDIA_TYPE, "csv"
    else:
        body = _export(snapshot).model_dump_json(indent=2) + "\n"
        media_type, extension = "application/json", "json"
    filename = export_filename(snapshot.project_name, snapshot.approval.baseline_number, extension)
    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def _export(snapshot: ApprovedSnapshot) -> BacklogExport:
    version, approval = snapshot.version, snapshot.approval
    return BacklogExport(
        schema_version="scopesteps.backlog-export.v1",
        exported_at=snapshot.exported_at,
        project=ExportedProject(id=version.project_id, name=snapshot.project_name),
        version=ExportedVersion(
            id=version.id,
            number=approval.baseline_number,
            state="approved",
            revision=version.revision,
            content_hash=version.content_hash,
            base_version_id=version.base_version_id,
            run_id=version.run_id,
            source_version_ids=[SourceVersionId(v) for v in version.source_version_ids],
            created_at=version.created_at,
            approved_by=approval.decided_by,
            approved_at=approval.decided_at,
        ),
        items=[
            ExportedItem(
                id=item.id,
                kind=item.kind,
                parent_id=item.parent_id,
                title=item.title,
                description=item.description,
                criteria=[
                    ExportedCriterion(
                        id=criterion.id,
                        text=criterion.text,
                        origin=criterion.origin,
                        evidence=evidence_refs(criterion.evidence),
                        confirmed_by=list(criterion.confirmed_by),
                    )
                    for criterion in item.criteria
                ],
                assumptions=list(item.assumptions),
                open_questions=list(item.open_questions),
                human_edited=item.human_edited,
            )
            for item in version.items
        ],
        decisions=[
            ExportedDecision(
                id=decision.id,
                kind=decision.kind,
                status=decision.status,
                subject=decision.subject,
                question=decision.question,
                why_it_matters=decision.why_it_matters,
                answer=decision.answer,
                decided_by=decision.decided_by,
                decided_at=decision.decided_at,
                affected_item_ids=list(decision.affected_item_ids),
                evidence=evidence_refs(decision.evidence),
            )
            for decision in version.decisions
        ],
        out_of_scope=[
            ScopeNoteResponse(
                kind=note.kind, summary=note.summary, evidence=evidence_refs(note.evidence)
            )
            for note in version.out_of_scope
        ],
        withheld_evidence_count=snapshot.withheld_evidence,
    )


def _response(version: domain.BacklogVersion) -> BacklogVersionResponse:
    blockers = [blocker_response(blocker) for blocker in version.blockers()]
    return BacklogVersionResponse(
        id=version.id,
        project_id=version.project_id,
        base_version_id=version.base_version_id,
        revision=version.revision,
        state=version.state.value,
        content_hash=version.content_hash,
        run_id=version.run_id,
        source_version_ids=[SourceVersionId(v) for v in version.source_version_ids],
        items=[item_response(item, version, blockers) for item in version.items],
        decisions=[
            BacklogDecision(
                id=decision.id,
                kind=decision.kind,
                status=decision.status,
                subject=decision.subject,
                question=decision.question,
                why_it_matters=decision.why_it_matters,
                evidence=evidence_refs(decision.evidence),
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
                kind=note.kind, summary=note.summary, evidence=evidence_refs(note.evidence)
            )
            for note in version.out_of_scope
        ],
        set_aside=[
            SetAsideNoteResponse(summary=note.summary, evidence=evidence_refs(note.evidence))
            for note in version.set_aside
        ],
        blockers=blockers,
        created_at=version.created_at,
    )
