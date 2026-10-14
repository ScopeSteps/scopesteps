from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.agent.application import runs
from scopesteps.agent.application.runs import AgentRuntime, RunView
from scopesteps.agent.application.schemas import DraftBacklogV1, parse_draft
from scopesteps.agent.application.steps import answer_blocks, source_blocks
from scopesteps.agent.client import RunId
from scopesteps.agent.domain.budget import MICROUSD_PER_USD
from scopesteps.agent.domain.run import RunChangedError
from scopesteps.agent.http.schemas import (
    AnswerRequest,
    BlockRef,
    ClarificationQuestion,
    CreateRunRequest,
    ProjectUsage,
    RunError,
    RunLimitsResponse,
    RunResponse,
    RunUsage,
)
from scopesteps.agent.infrastructure.repository import (
    SqlCandidateStore,
    SqlPassageReader,
    SqlRunRepository,
)
from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.client import find_candidate
from scopesteps.evidence.client import EvidenceRef
from scopesteps.identity.client import (
    ProjectAccess,
    ProjectAccessResolver,
    get_project_access,
    get_project_access_resolver,
)
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import IdempotencyKey, SessionDep
from scopesteps.projects.client import PeopleRecorder, ProjectId, get_people_recorder
from scopesteps.sources.client import SourceBlockId, SourceVersionId

router = APIRouter(tags=["agent"])

ProjectAccessDep = Annotated[ProjectAccess, Depends(get_project_access)]
ResolverDep = Annotated[ProjectAccessResolver, Depends(get_project_access_resolver)]


def get_agent_runtime(request: Request) -> AgentRuntime:
    runtime: AgentRuntime = request.app.state.agent_runtime
    return runtime


RuntimeDep = Annotated[AgentRuntime, Depends(get_agent_runtime)]


@router.post("/projects/{project_id}/runs", status_code=status.HTTP_202_ACCEPTED)
def create_run(
    project_id: ProjectId,
    body: CreateRunRequest,
    idempotency_key: IdempotencyKey,
    access: ProjectAccessDep,
    runtime: RuntimeDep,
    session: SessionDep,
) -> RunResponse:
    """Create a run pinned to the given source versions. Nothing is sent to the model until the
    first advance."""
    view = _committing(
        session,
        lambda: runs.create_run(
            SqlRunRepository(session),
            audit_recorder(session),
            SqlPassageReader(session),
            runtime,
            access,
            runs.CreateRun(
                idempotency_key=idempotency_key,
                mode=body.mode,
                source_version_ids=tuple(body.source_version_ids),
            ),
            utc_now(),
        ),
    )
    return _response(session, view, runtime)


@router.get("/runs/{run_id}")
def get_run(
    run_id: RunId, resolve: ResolverDep, runtime: RuntimeDep, session: SessionDep
) -> RunResponse:
    view = runs.get_run(SqlRunRepository(session), resolve, run_id)
    return _response(session, view, runtime)


@router.post("/runs/{run_id}/advance")
def advance_run(
    run_id: RunId,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    runtime: RuntimeDep,
    record_people: Annotated[PeopleRecorder, Depends(get_people_recorder)],
    session: SessionDep,
) -> RunResponse:
    """Execute one bounded step: a model call, its tools, or the draft with its single repair.

    Call again while the status is `created` or `running`. 409 `RUN_BUSY` means another request
    holds the run's lease; retry after a short wait. A run that is waiting or finished is
    returned unchanged.
    """
    view = _committing(
        session,
        lambda: runs.advance_run(
            SqlRunRepository(session),
            audit_recorder(session),
            SqlPassageReader(session),
            SqlCandidateStore(session),
            record_people,
            runtime,
            resolve,
            run_id,
            idempotency_key,
            utc_now,
        ),
    )
    return _response(session, view, runtime)


@router.post("/runs/{run_id}/answers")
def answer_question(
    run_id: RunId,
    body: AnswerRequest,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    runtime: RuntimeDep,
    session: SessionDep,
) -> RunResponse:
    """Answer or skip one question. When the round is complete the run returns to `running`."""
    view = _committing(
        session,
        lambda: runs.answer_question(
            SqlRunRepository(session),
            audit_recorder(session),
            resolve,
            run_id,
            runs.AnswerQuestion(
                idempotency_key=idempotency_key,
                question_id=body.question_id,
                answer=None if body.skip else body.answer,
            ),
            utc_now(),
        ),
    )
    return _response(session, view, runtime)


@router.post("/runs/{run_id}/cancel")
def cancel_run(
    run_id: RunId,
    idempotency_key: IdempotencyKey,
    resolve: ResolverDep,
    runtime: RuntimeDep,
    session: SessionDep,
) -> RunResponse:
    view = _committing(
        session,
        lambda: runs.cancel_run(
            SqlRunRepository(session),
            audit_recorder(session),
            resolve,
            run_id,
            idempotency_key,
            utc_now(),
        ),
    )
    return _response(session, view, runtime)


def _committing(session: Session, action: Callable[[], RunView]) -> RunView:
    try:
        return action()
    except IntegrityError as error:
        # A concurrent request won a unique constraint (the same Idempotency-Key, a step number,
        # or the run's one candidate). Nothing of this request's last transaction was stored.
        session.rollback()
        raise RunChangedError("Another request for this run finished first. Try again.") from error


def _usd(microusd: int | None) -> str | None:
    return None if microusd is None else f"{microusd / MICROUSD_PER_USD:.6f}"


def _response(session: Session, view: RunView, runtime: AgentRuntime) -> RunResponse:
    run = view.run
    passages = SqlPassageReader(session).load(run.project_id, run.inputs.source_version_ids)
    pinned = dict(zip((block.id for block in source_blocks(passages)), passages, strict=True))
    by_label = {label: passage.block_id for label, passage in pinned.items()}
    answers = {q.answer_label: q.id for q in view.questions if q.answer_label}
    refs = [
        BlockRef(label=label, source_block_id=SourceBlockId(block_id), question_id=None)
        for label, block_id in by_label.items()
    ] + [
        BlockRef(label=block.id, source_block_id=None, question_id=answers[block.id])
        for block in answer_blocks(view.questions)
    ]
    limits = run.inputs.limits
    draft = None if run.draft is None else parse_draft(run.draft)
    return RunResponse(
        id=run.id,
        project_id=run.project_id,
        mode=run.mode,
        status=run.status.value,
        stage=run.stage.value,
        revision=run.revision,
        source_version_ids=[SourceVersionId(v) for v in run.inputs.source_version_ids],
        provider=run.inputs.provider,
        model_id=run.inputs.model_id,
        fallback_reason=run.inputs.fallback_reason,
        prompt_version=run.inputs.prompt_version,
        usage=RunUsage(
            model_turns=run.counters.model_turns,
            tool_calls=run.counters.tool_calls,
            clarification_rounds=run.clarification_rounds,
            input_tokens=run.totals.input_tokens,
            output_tokens=run.totals.output_tokens,
            thinking_tokens=run.totals.thinking_tokens,
            total_tokens=run.counters.total_tokens,
            cost_usd_estimate=_usd(run.totals.cost_microusd) or "0",
        ),
        limits=RunLimitsResponse(
            max_turns=limits.max_turns,
            max_tool_calls=limits.max_tool_calls,
            max_clarification_rounds=run.inputs.max_clarification_rounds,
            max_total_tokens=limits.max_total_tokens,
            max_cost_usd=_usd(limits.max_cost_microusd),
        ),
        project_usage=ProjectUsage(
            cost_usd_estimate=_usd(view.project_cost_microusd) or "0",
            cost_limit_usd=_usd(runtime.project_cost_limit_microusd),
        ),
        questions=[
            ClarificationQuestion(
                id=question.id,
                subject=question.subject,
                text=question.text,
                why_it_matters=question.why_it_matters,
                evidence_block_ids=[
                    SourceBlockId(by_label[label])
                    for label in question.block_labels
                    if label in by_label
                ],
                evidence=[
                    EvidenceRef(
                        source_version_id=pinned[label].source_version_id,
                        block_id=pinned[label].block_id,
                    )
                    for label in question.block_labels
                    if label in pinned
                ],
                status=question.status.value,
                round=question.round,
                answer=question.answer,
                answered_by=question.answered_by,
                answered_at=question.answered_at,
            )
            for question in view.questions
        ],
        draft=None if isinstance(draft, DraftBacklogV1) else draft,
        block_refs=refs,
        problems=list(run.problems),
        candidate_version_id=find_candidate(session, run.id),
        error=None
        if run.error is None
        else RunError(
            code=run.error.code, message=run.error.message, retryable=run.error.retryable
        ),
    )
