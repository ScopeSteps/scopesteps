from collections.abc import Callable, Mapping
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.agent.application import change_requests, conversation, runs
from scopesteps.agent.application.conversation import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from scopesteps.agent.application.reply_tools import GET_STORY, LIST_OPEN_DECISIONS
from scopesteps.agent.application.runs import AgentRuntime, RunView
from scopesteps.agent.application.schemas import DraftBacklogV1, parse_draft
from scopesteps.agent.application.steps import answer_blocks, source_blocks
from scopesteps.agent.application.tools import LOOKUP_SOURCE
from scopesteps.agent.client import REPLAY_PROVIDER, RunId
from scopesteps.agent.domain.budget import MICROUSD_PER_USD
from scopesteps.agent.domain.conversation import Message
from scopesteps.agent.domain.ids import MessageId
from scopesteps.agent.domain.run import Question, Run, RunChangedError
from scopesteps.agent.domain.suggestion import Suggestion
from scopesteps.agent.http.schemas import (
    ActiveRun,
    AgentModelResponse,
    AnswerRequest,
    BlockRef,
    ClarificationQuestion,
    ConversationResponse,
    CreateRunRequest,
    LookupTool,
    MessageAuthor,
    MessageCitation,
    MessageClaim,
    MessageQuestion,
    MessageResponse,
    MessageSuggestion,
    PostMessageRequest,
    PostMessageResponse,
    ProjectUsage,
    RunError,
    RunLimitsResponse,
    RunLookup,
    RunResponse,
    RunUsage,
    SuggestionStatusRequest,
)
from scopesteps.agent.infrastructure.repository import (
    SqlCandidateStore,
    SqlChangeRequests,
    SqlChangeStore,
    SqlDraftAnswers,
    SqlPassageReader,
    SqlProjectContext,
    SqlRunRepository,
)
from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.client import BacklogVersionId, find_candidate
from scopesteps.change_control.client import ChangeOutcome, ChangeOutcomeRecorder
from scopesteps.evidence.client import EvidenceRef
from scopesteps.identity.client import (
    ProjectAccess,
    ProjectAccessResolver,
    get_project_access,
    get_project_access_resolver,
)
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import IdempotencyKey, SessionDep
from scopesteps.kernel.errors import InvalidInputError
from scopesteps.projects.client import (
    PeopleRecorder,
    ProjectId,
    SpeakerIdentityReader,
    get_people_recorder,
    get_speaker_identity_reader,
)
from scopesteps.sources.client import SourceBlockId, SourceVersionId

router = APIRouter(tags=["agent"])

ProjectAccessDep = Annotated[ProjectAccess, Depends(get_project_access)]
ResolverDep = Annotated[ProjectAccessResolver, Depends(get_project_access_resolver)]


def get_agent_runtime(request: Request) -> AgentRuntime:
    runtime: AgentRuntime = request.app.state.agent_runtime
    return runtime


RuntimeDep = Annotated[AgentRuntime, Depends(get_agent_runtime)]


@router.get("/agent/model")
def get_agent_model(runtime: RuntimeDep) -> AgentModelResponse:
    """The model new runs are created with, so the app can say when it is a replay."""
    primary = runtime.primary
    if primary is None:
        return AgentModelResponse(provider=None, model_id=None, replay=False)
    return AgentModelResponse(
        provider=primary.provider_name,
        model_id=primary.model_id,
        replay=primary.provider_name == REPLAY_PROVIDER,
    )


@router.post("/projects/{project_id}/runs", status_code=status.HTTP_202_ACCEPTED)
def create_run(
    project_id: ProjectId,
    body: CreateRunRequest,
    idempotency_key: IdempotencyKey,
    access: ProjectAccessDep,
    runtime: RuntimeDep,
    identities: Annotated[SpeakerIdentityReader, Depends(get_speaker_identity_reader)],
    session: SessionDep,
) -> RunResponse:
    """Create a run. Nothing is sent to the model until the first advance.

    An initial run is pinned to the given source versions, and starts only once every speaker in
    them is confirmed (409 `SPEAKERS_UNCONFIRMED`, ADR 0015). A change run records the change
    request against the baseline the requester saw (409 `BASELINE_CHANGED` if it is no longer
    the current one, `BASELINE_REQUIRED` before any) and pins that baseline's sources and the
    request's text, exactly as a change request sent in the conversation does.
    """
    store = SqlRunRepository(session)
    if body.mode == "change":
        if body.base_version_id is None or body.base_content_hash is None or not body.request_text:
            # CreateRunRequest already refuses this; the check narrows the types.
            raise InvalidInputError("A change run needs a baseline and the request's text")
        command = change_requests.CreateChangeRun(
            idempotency_key=idempotency_key,
            request_text=body.request_text,
            base_version_id=body.base_version_id,
            base_content_hash=body.base_content_hash,
        )
        run = _committing_run(
            session,
            lambda: change_requests.create_change_run(
                store,
                audit_recorder(session),
                SqlProjectContext(session),
                SqlChangeRequests(session),
                runtime,
                access,
                command,
                utc_now(),
            ),
        )
        view = RunView(
            run, tuple(store.questions(run.id)), store.project_cost_microusd(run.project_id)
        )
        return _response(session, view, runtime)
    view = _committing(
        session,
        lambda: runs.create_run(
            store,
            audit_recorder(session),
            SqlPassageReader(session, identities),
            runtime,
            access,
            runs.CreateRun(
                idempotency_key=idempotency_key,
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
    identities: Annotated[SpeakerIdentityReader, Depends(get_speaker_identity_reader)],
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
            SqlPassageReader(session, identities),
            SqlCandidateStore(session),
            SqlChangeStore(session),
            SqlChangeRequests(session),
            record_people,
            SqlProjectContext(session),
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
    """Answer or skip one question. When the round is complete the run returns to `running`.

    For a question already answered or skipped, it changes that answer (send
    `expected_revision`): while the round is open, or once the draft is saved, which then moves
    to its next revision. 409 `ANSWER_LOCKED` once that draft is approved, 409
    `RUN_STATE_INVALID` while the agent is using the answers.
    """
    view = _committing(
        session,
        lambda: runs.answer_question(
            SqlRunRepository(session),
            audit_recorder(session),
            SqlDraftAnswers(session),
            resolve,
            run_id,
            runs.AnswerQuestion(
                idempotency_key=idempotency_key,
                question_id=body.question_id,
                answer=None if body.skip else body.answer,
                expected_revision=body.expected_revision,
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
            SqlChangeRequests(session),
            resolve,
            run_id,
            idempotency_key,
            utc_now(),
        ),
    )
    return _response(session, view, runtime)


@router.get("/projects/{project_id}/messages")
def list_messages(
    project_id: ProjectId,
    access: ProjectAccessDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    cursor: Annotated[
        str | None, Query(max_length=200, description="`next_cursor` of the previous page.")
    ] = None,
) -> ConversationResponse:
    """The project's conversation, newest first, and any agent work in progress. Every member
    sees the same thread."""
    page = conversation.list_conversation(
        SqlRunRepository(session), access, limit=limit, cursor=cursor
    )
    return ConversationResponse(
        messages=[
            _message(message, page.questions, page.suggestions.get(message.id))
            for message in page.messages
        ],
        next_cursor=page.next_cursor,
        active_run=None if page.active_run is None else _active(page.active_run),
    )


@router.put("/projects/{project_id}/messages/{message_id}/suggestion")
def decide_suggestion(
    project_id: ProjectId,
    message_id: MessageId,
    body: SuggestionStatusRequest,
    idempotency_key: IdempotencyKey,
    access: ProjectAccessDep,
    session: SessionDep,
) -> MessageSuggestion:
    """Record that a person accepted or dismissed a reply's suggestion (ADR 0013). Needs the
    editor or approver role. Accepting runs nothing: call the action's own endpoint first, which
    repeats every check, then record `accepted` here.

    409 `SUGGESTION_CHANGED` means `expected_revision` is stale; 409
    `SUGGESTION_ALREADY_DECIDED` means it was decided the other way. Recording the status it
    already has returns it unchanged, so the key is required but no receipt is kept.
    """
    suggestion = conversation.decide_suggestion(
        SqlRunRepository(session),
        access,
        conversation.DecideSuggestion(message_id, body.status, body.expected_revision),
        utc_now(),
    )
    return _suggestion(suggestion)


@router.post("/projects/{project_id}/messages", status_code=status.HTTP_202_ACCEPTED)
def post_message(
    project_id: ProjectId,
    body: PostMessageRequest,
    idempotency_key: IdempotencyKey,
    access: ProjectAccessDep,
    runtime: RuntimeDep,
    session: SessionDep,
) -> PostMessageResponse:
    """Send a message to the agent. It is stored with a run, which the client advances
    (`POST /runs/{id}/advance`) and stops with `POST /runs/{id}/cancel`: a reply run for a free
    message (a read-only, cited reply), a change run for a `change_request` (an analysis against
    the baseline, ADR 0011).

    409 `AGENT_BUSY` while a run in the project is created or running, or another change request
    is being analysed (`details.run_id` names it). A `change_request` needs an approved
    baseline (409 `BASELINE_REQUIRED`) and must name it as the requester saw it (409
    `BASELINE_CHANGED`).
    """
    store = SqlRunRepository(session)
    try:
        posted = conversation.post_message(
            store,
            audit_recorder(session),
            SqlProjectContext(session),
            SqlChangeRequests(session),
            runtime,
            access,
            conversation.PostMessage(
                idempotency_key=idempotency_key,
                text=body.text,
                kind=body.kind,
                base_version_id=body.base_version_id,
                base_content_hash=body.base_content_hash,
            ),
            utc_now(),
        )
    except IntegrityError as error:
        # A concurrent request took the conversation's turn or the same Idempotency-Key first.
        session.rollback()
        raise RunChangedError("Another request finished first. Try again.") from error
    view = RunView(
        posted.run, tuple(store.questions(posted.run.id)), store.project_cost_microusd(project_id)
    )
    return PostMessageResponse(
        message=_message(posted.message, {}), run=_response(session, view, runtime)
    )


def resolve_change_outcome_recorder(session: SessionDep) -> ChangeOutcomeRecorder:
    """The implementation the composition root binds to
    `change_control.client.get_change_outcome_recorder`, writing in the request's session."""
    store = SqlRunRepository(session)

    def record(outcome: ChangeOutcome) -> None:
        change_requests.record_change_outcome(store, outcome)

    return record


def _active(run: Run) -> ActiveRun:
    return ActiveRun(id=run.id, mode=run.mode, status=run.status.value)


LOOKUP_TOOLS: dict[str, LookupTool] = {
    LOOKUP_SOURCE.name: "lookup_source",
    GET_STORY: "get_story",
    LIST_OPEN_DECISIONS: "list_open_decisions",
}


def _suggestion(suggestion: Suggestion) -> MessageSuggestion:
    proposed = suggestion.proposed
    return MessageSuggestion(
        kind=suggestion.kind,
        status=suggestion.status,
        revision=suggestion.revision,
        request_text=proposed.request_text,
        version_id=None if proposed.version_id is None else BacklogVersionId(proposed.version_id),
        decision_id=proposed.decision_id,
        decision_subject=proposed.decision_subject,
        answer=proposed.answer,
        decided_by=suggestion.decided_by,
        decided_at=suggestion.decided_at,
    )


def _lookups(session: Session, run: Run) -> list[RunLookup]:
    if run.mode != "reply":
        return []
    lookups: list[RunLookup] = []
    for step in SqlRunRepository(session).steps(run.id):
        if step.kind == "tool" and step.name in LOOKUP_TOOLS:
            found = step.detail.get("found", 0)
            lookups.append(
                RunLookup(
                    tool=LOOKUP_TOOLS[step.name],
                    found=found if isinstance(found, int) else 0,
                    refused=step.detail.get("refused") is True,
                )
            )
    return lookups


def _message(
    message: Message,
    questions: Mapping[UUID, Question],
    suggestion: Suggestion | None = None,
) -> MessageResponse:
    question = None if message.question_id is None else questions.get(message.question_id)
    return MessageResponse(
        suggestion=None if suggestion is None else _suggestion(suggestion),
        id=message.id,
        role=message.role.value,
        kind=message.kind.value,
        text=message.text,
        created_at=message.created_at,
        author=None
        if message.author_id is None
        else MessageAuthor(user_id=message.author_id, display_name=message.author_name or ""),
        run_id=message.run_id,
        question_id=message.question_id,
        event=None if message.event is None else message.event.value,
        change_request_id=message.change_request_id,
        baseline_version=message.baseline_version,
        claims=[
            MessageClaim(
                text=claim.text,
                basis=claim.basis,
                citations=[
                    MessageCitation(
                        quote=citation.quote,
                        evidence=None
                        if citation.source_version_id is None or citation.block_id is None
                        else EvidenceRef(
                            source_version_id=SourceVersionId(citation.source_version_id),
                            block_id=SourceBlockId(citation.block_id),
                            quote=citation.quote,
                        ),
                        question_id=citation.question_id,
                    )
                    for citation in claim.citations
                ],
            )
            for claim in message.claims
        ],
        question=None
        if question is None
        else MessageQuestion(
            id=question.id,
            run_id=question.run_id,
            round=question.round,
            subject=question.subject,
            why_it_matters=question.why_it_matters,
            status=question.status.value,
            answer=question.answer,
            answered_by=question.answered_by,
            answered_at=question.answered_at,
        ),
    )


def _committing_run(session: Session, action: Callable[[], Run]) -> Run:
    try:
        return action()
    except IntegrityError as error:
        # A concurrent request took the conversation's turn, the next change request number or
        # the same Idempotency-Key first. Nothing of this request was stored.
        session.rollback()
        raise RunChangedError("Another request finished first. Try again.") from error


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
    # A change run's draft is its change set; its review is the change set route.
    draft = None if run.draft is None or run.mode != "initial" else parse_draft(run.draft)
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
        lookups=_lookups(session, run),
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
        change_request_id=None
        if run.inputs.change is None
        else run.inputs.change.change_request_id,
        base_version_id=None
        if run.inputs.change is None
        else BacklogVersionId(run.inputs.change.base_version_id),
        error=None
        if run.error is None
        else RunError(
            code=run.error.code, message=run.error.message, retryable=run.error.retryable
        ),
    )
