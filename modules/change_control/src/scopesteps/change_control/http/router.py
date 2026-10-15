from collections.abc import Callable, Collection
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.client import (
    BacklogVersionId,
    DecisionId,
    DecisionReader,
    ItemId,
    VersionDecision,
    evidence_refs,
    item_change_responses,
)
from scopesteps.change_control.application import change_requests, decisions
from scopesteps.change_control.application.change_requests import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ListedRequest,
)
from scopesteps.change_control.application.decisions import ChangeOutcomeRecorder, DecisionView
from scopesteps.change_control.client import get_change_outcome_recorder
from scopesteps.change_control.domain.errors import DecisionInProgressError
from scopesteps.change_control.domain.ids import ChangeRequestId
from scopesteps.change_control.http.schemas import (
    ApproveRequest,
    ChangeOperation,
    ChangeRequestAuthor,
    ChangeRequestPage,
    ChangeRequestResponse,
    ChangeSetResponse,
    ChangeSummaryResponse,
    DecisionResponse,
    ImpactNote,
    RejectRequest,
    RemovedExclusion,
    ScopeReversalResponse,
)
from scopesteps.change_control.infrastructure.repository import (
    BacklogVersionReader,
    BacklogVersions,
    SqlChangeRequestStore,
    SqlDecisionStore,
)
from scopesteps.identity.client import (
    ProjectAccess,
    ProjectAccessResolver,
    get_project_access,
    get_project_access_resolver,
)
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import IdempotencyKey, SessionDep
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceVersionId

router = APIRouter(tags=["change_control"])

ResolverDep = Annotated[ProjectAccessResolver, Depends(get_project_access_resolver)]
OutcomesDep = Annotated[ChangeOutcomeRecorder, Depends(get_change_outcome_recorder)]


@router.post("/backlogs/{version_id}/approve")
def approve_version(
    version_id: BacklogVersionId,
    body: ApproveRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    outcomes: OutcomesDep,
    session: SessionDep,
) -> DecisionResponse:
    """Approve the draft, or a change candidate in review, as the project's next baseline. Needs
    the approver role.

    A change candidate also needs every scope decision recorded and reversed: 409
    `SCOPE_DECISION_REQUIRED` or `SCOPE_KEPT` (only rejection is left) list them in
    `details.decision_ids`. Its change request moves to approved, and `change.approved` is posted
    to the project's conversation, in the same transaction.
    Runs every approval check again; 409 `APPROVAL_BLOCKED` lists them in `details.checks`.
    409 `VERSION_CHANGED` or `BASELINE_CHANGED` means what was reviewed is stale: reload and
    review again rather than retrying.
    """
    view = _deciding(
        session,
        lambda: decisions.approve(
            BacklogVersions(session),
            SqlDecisionStore(session),
            SqlChangeRequestStore(session),
            audit_recorder(session),
            outcomes,
            resolve,
            version_id,
            decisions.Approve(
                idempotency_key=idempotency_key,
                expected_revision=body.expected_revision,
                content_hash=body.content_hash,
                expected_baseline_id=body.expected_baseline_id,
            ),
            utc_now(),
        ),
    )
    return _response(view)


@router.post("/backlogs/{version_id}/reject")
def reject_version(
    version_id: BacklogVersionId,
    body: RejectRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    outcomes: OutcomesDep,
    session: SessionDep,
) -> DecisionResponse:
    """Reject the draft or change candidate; the baseline stays as it is. Needs the approver
    role. A candidate's change request moves to rejected, and `change.rejected` is posted to the
    project's conversation, in the same transaction."""
    view = _deciding(
        session,
        lambda: decisions.reject(
            BacklogVersions(session),
            SqlDecisionStore(session),
            SqlChangeRequestStore(session),
            audit_recorder(session),
            outcomes,
            resolve,
            version_id,
            decisions.Reject(
                idempotency_key=idempotency_key,
                expected_revision=body.expected_revision,
                reason=body.reason,
            ),
            utc_now(),
        ),
    )
    return _response(view)


@router.get("/projects/{project_id}/change-requests")
def list_change_requests(
    project_id: ProjectId,
    access: Annotated[ProjectAccess, Depends(get_project_access)],
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    cursor: Annotated[
        str | None, Query(max_length=200, description="`next_cursor` of the previous page.")
    ] = None,
) -> ChangeRequestPage:
    """The project's change requests, newest first, each with its status and, once analysed,
    the counts of items its candidate adds, changes and removes. Any member may read them."""
    page = change_requests.list_change_requests(
        SqlChangeRequestStore(session),
        BacklogVersionReader(session),
        access,
        limit=limit,
        cursor=cursor,
    )
    return ChangeRequestPage(
        change_requests=[_request(listed) for listed in page.requests],
        next_cursor=page.next_cursor,
    )


@router.get("/change-requests/{change_request_id}")
def get_change_request(
    change_request_id: ChangeRequestId, resolve: ResolverDep, session: SessionDep
) -> ChangeRequestResponse:
    listed = change_requests.get_change_request(
        SqlChangeRequestStore(session), BacklogVersionReader(session), resolve, change_request_id
    )
    return _request(listed)


@router.get("/backlogs/{version_id}/change-set")
def get_change_set(
    version_id: BacklogVersionId, resolve: ResolverDep, session: SessionDep
) -> ChangeSetResponse:
    """What a candidate in review changes in the baseline it was made from, matched by stable
    item and criterion ids, with the analysis's reasons, scope decisions and impact notes. 404
    for a version no change request proposed."""
    change_set = change_requests.get_change_set(
        SqlChangeRequestStore(session), BacklogVersionReader(session), resolve, version_id
    )
    request = change_set.request
    rationales = {note.item_id: note.note for note in request.rationales}
    return ChangeSetResponse(
        id=change_set.id,
        change_request_id=request.id,
        base_version_id=change_set.base.id,
        base_content_hash=change_set.base.content_hash,
        candidate_version_id=change_set.candidate.id,
        candidate_content_hash=change_set.candidate.content_hash,
        operations=[
            ChangeOperation(**change.model_dump(), rationale=rationales.get(change.item_id))
            for change in item_change_responses(
                change_set.base, change_set.candidate, change_set.changes
            )
        ],
        removed_exclusions=[
            RemovedExclusion(summary=note.summary, evidence=evidence_refs(note.evidence))
            for note in change_set.removed_exclusions
        ],
        scope_decisions=[
            ScopeReversalResponse(
                decision_id=DecisionId(reversal.decision_id),
                reverses=reversal.reverses,
                summary=reversal.summary,
                reversed_decision_id=None
                if reversal.reversed_decision_id is None
                else DecisionId(reversal.reversed_decision_id),
            )
            for reversal in request.scope_reversals
        ],
        open_decision_ids=list(change_set.open_decision_ids),
        impacts=[
            ImpactNote(item_id=ItemId(note.item_id), note=note.note) for note in request.impacts
        ],
    )


def _request(listed: ListedRequest) -> ChangeRequestResponse:
    request = listed.request
    summary = request.summary
    return ChangeRequestResponse(
        id=request.id,
        project_id=request.project_id,
        number=request.number,
        text=request.text,
        requested_by=ChangeRequestAuthor(
            user_id=request.requested_by, display_name=request.requested_by_name
        ),
        requested_at=request.requested_at,
        status=request.status.value,
        base_version_id=BacklogVersionId(request.base_version_id),
        base_version_number=listed.base_version_number,
        base_content_hash=request.base_content_hash,
        source_version_id=SourceVersionId(request.source_version_id),
        run_id=request.run_id,
        candidate_version_id=None
        if request.candidate_version_id is None
        else BacklogVersionId(request.candidate_version_id),
        summary=None
        if summary is None
        else ChangeSummaryResponse(
            added=summary.added, changed=summary.changed, removed=summary.removed
        ),
        analysis=request.analysis,
        failure=request.failure,
        analyzed_at=request.analyzed_at,
        approved_version_number=listed.approved_version_number,
    )


def resolve_decision_reader(session: SessionDep) -> DecisionReader:
    """The implementation the composition root binds to `backlog.client.get_decision_reader`."""
    store = SqlDecisionStore(session)

    def read(version_ids: Collection[BacklogVersionId]) -> dict[BacklogVersionId, VersionDecision]:
        return {
            version_id: VersionDecision(
                version_id=version_id,
                decision=decision.decision,
                decided_by=decision.decided_by,
                decided_at=decision.decided_at,
                baseline_number=decision.baseline_number,
            )
            for version_id, decision in store.of_versions(version_ids).items()
        }

    return read


def _deciding(session: Session, decide: Callable[[], DecisionView]) -> DecisionView:
    try:
        view = decide()
        session.commit()
    except IntegrityError as error:
        # A concurrent request decided the version, took the next baseline number or used the
        # same Idempotency-Key first. Nothing of this request was stored.
        session.rollback()
        raise DecisionInProgressError(
            "Another decision finished first. Reload the backlog to see where it stands."
        ) from error
    return view


def _response(view: DecisionView) -> DecisionResponse:
    decision = view.decision
    return DecisionResponse(
        id=decision.id,
        version_id=decision.version_id,
        decision=decision.decision,
        decided_by=decision.decided_by,
        revision=decision.revision,
        content_hash=decision.content_hash,
        decided_at=decision.decided_at,
        baseline_version=decision.baseline_number,
        current_baseline_id=None
        if view.current_baseline is None
        else view.current_baseline.version_id,
        change_request_id=None if view.change_request is None else view.change_request.id,
        change_request_status=None
        if view.change_request is None
        else view.change_request.status.value,
    )
