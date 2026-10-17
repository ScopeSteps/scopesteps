"""Run use cases. Each advance executes one bounded step:

1. a short transaction checks the revision and takes a lease;
2. the model is called with no transaction open;
3. a short transaction commits the step only if the run is still at the leased revision.

A result that loses the race (the run was cancelled, or its expired lease was taken over) is
discarded, but its usage still counts, because the provider may have billed for it.
"""

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from scopesteps.agent.application.changing import (
    ChangeResult,
    analysis_blocks,
    baseline_labels,
)
from scopesteps.agent.application.checks import MAX_REPORTED
from scopesteps.agent.application.fallback import AVAILABILITY_ERRORS, CircuitBreaker, ServedModel
from scopesteps.agent.application.ports import (
    CandidateStore,
    ChangeRequests,
    ChangeStore,
    DraftAnswers,
    MessageCursor,
    ModelProvider,
    Passage,
    PassageReader,
    ProjectContext,
    Receipt,
    RunStore,
)
from scopesteps.agent.application.replying import earlier_messages, resolve_claims
from scopesteps.agent.application.steps import (
    AGENT_PROMPT_VERSION,
    AGENT_SCHEMA_VERSION,
    ChangeInput,
    ReplyInput,
    StepContext,
    StepOutcome,
    answers_turn,
    request_version,
    source_blocks,
    take_reply_step,
    take_step,
)
from scopesteps.agent.domain.budget import RunLimits
from scopesteps.agent.domain.conversation import (
    AgentBusyError,
    ConversationEvent,
    Message,
    MessageKind,
    agent_busy,
    answer_message,
    event_message,
    question_message,
    reply_message,
)
from scopesteps.agent.domain.ids import QuestionId, RunId, StepId
from scopesteps.agent.domain.run import (
    ADVANCEABLE,
    TERMINAL,
    AnswerLockedError,
    Lease,
    Question,
    QuestionStatus,
    Run,
    RunBusyError,
    RunChangedError,
    RunError,
    RunInputs,
    RunStage,
    RunStateError,
    RunStatus,
    RunStep,
)
from scopesteps.agent.domain.suggestion import Suggestion
from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.backlog.client import DecisionId, ItemId, ItemRef, VersionNotDraftError
from scopesteps.change_control.client import ChangeAnalysis, ItemNote, ScopeReversal
from scopesteps.identity.client import ProjectAccess, ProjectAccessResolver, Role
from scopesteps.kernel.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    UnavailableError,
)
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import PeopleRecorder
from scopesteps.sources.client import SourceRemovedError, SourceVersionId


class IdempotencyKeyReusedError(ConflictError):
    code = "IDEMPOTENCY_KEY_REUSED"


class ModelNotConfiguredError(UnavailableError):
    code = "MODEL_NOT_CONFIGURED"


class RunModelChangedError(ConflictError):
    """The run's pinned model is not the one this process serves. Its saved conversation is in
    that provider's format, and mixing models would make the run's results meaningless."""

    code = "RUN_MODEL_CHANGED"


@dataclass(frozen=True)
class AgentRuntime:
    """What the composition root provides: the primary model, an optional backup, and the limits
    new runs pin. Without `fallback` a run only ever uses the primary."""

    provider: ModelProvider | None
    provider_name: str
    model_id: str
    limits: RunLimits
    max_clarification_rounds: int
    project_cost_limit_microusd: int | None
    lease_seconds: float
    fallback: ServedModel | None = None
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    @property
    def primary(self) -> ServedModel | None:
        if self.provider is None:
            return None
        return ServedModel(self.provider, self.provider_name, self.model_id)

    def served(self, key: tuple[str, str]) -> ServedModel | None:
        """The configured model a run is pinned to, or None if this process does not serve it."""
        return next(
            (model for model in (self.primary, self.fallback) if model and model.key == key),
            None,
        )


@dataclass(frozen=True)
class RunView:
    run: Run
    questions: tuple[Question, ...]
    project_cost_microusd: int


@dataclass(frozen=True)
class CreateRun:
    """An initial run. A change run is created with its change request (`change_requests`)."""

    idempotency_key: str
    source_version_ids: tuple[SourceVersionId, ...]


def create_run(
    store: RunStore,
    audit: AuditRecorder,
    passages: PassageReader,
    runtime: AgentRuntime,
    access: ProjectAccess,
    command: CreateRun,
    now: datetime,
) -> RunView:
    access.require_role(Role.EDITOR)
    fingerprint = _fingerprint("create", [str(v) for v in command.source_version_ids])
    replay = _replay(store, access, command.idempotency_key, "create", fingerprint)
    if replay is not None:
        return _view(store, replay)
    primary = runtime.primary
    if primary is None:
        raise ModelNotConfiguredError("No model provider is configured (MODEL_PROVIDER)")
    _check_sources(passages, access, command.source_version_ids)
    # A reply in progress holds the project's turn (ADR 0010). Runs were never limited to one
    # at a time, so only a reply blocks here.
    busy = store.active_run(access.project_id)
    if busy is not None and busy.mode == "reply" and busy.status in ADVANCEABLE:
        raise agent_busy(busy)
    if not store.claim_turn(access.project_id):
        raise AgentBusyError("A message was sent at the same time. Wait for its reply.")
    served, fallback_reason = primary, None
    if runtime.fallback is not None and runtime.breaker.is_open():
        served, fallback_reason = runtime.fallback, "primary_circuit_open"
    run = Run(
        id=RunId(new_id()),
        project_id=access.project_id,
        mode="initial",
        status=RunStatus.CREATED,
        stage=RunStage.EXPLORE,
        revision=1,
        inputs=RunInputs(
            source_version_ids=command.source_version_ids,
            provider=served.provider_name,
            model_id=served.model_id,
            fallback_reason=fallback_reason,
            prompt_version=AGENT_PROMPT_VERSION,
            schema_version=AGENT_SCHEMA_VERSION,
            limits=runtime.limits,
            max_clarification_rounds=runtime.max_clarification_rounds,
        ),
        created_by=access.actor.user_id,
        created_at=now,
        updated_at=now,
    )
    store.add_run(run)
    _add_receipt(store, access, command.idempotency_key, "create", run.id, fingerprint, now)
    sources = len(command.source_version_ids)
    started = f"Started a run on {sources} source {'version' if sources == 1 else 'versions'}"
    audit.record(
        project_id=run.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.RUN_STARTED,
        subjects=(Subject(SubjectKind.RUN, run.id),),
        summary=started,
        occurred_at=now,
    )
    store.add_messages(
        [
            event_message(
                run.id,
                run.project_id,
                ConversationEvent.RUN_STARTED,
                f"{started}.",
                now,
                author=access.actor,
            )
        ]
    )
    store.commit()
    return _view(store, run)


def _check_sources(
    passages: PassageReader, access: ProjectAccess, version_ids: Sequence[SourceVersionId]
) -> None:
    """A run may pin any set of the project's source versions, each once, from any source the
    project has not removed."""
    if len(set(version_ids)) != len(version_ids):
        raise InvalidInputError(
            "Each source version may be selected once", details={"field": "source_version_ids"}
        )
    if not passages.load(access.project_id, version_ids):
        raise NotFoundError("The selected sources have no paragraphs")
    removed = passages.removed(access.project_id, version_ids)
    if removed:
        raise SourceRemovedError(
            "A selected source was removed from the project. Choose its current sources.",
            details={"source_version_ids": sorted(str(v) for v in removed)},
        )


def get_run(store: RunStore, resolve: ProjectAccessResolver, run_id: RunId) -> RunView:
    run = _load(store, resolve, run_id, Role.VIEWER)
    return _view(store, run)


def cancel_run(
    store: RunStore,
    audit: AuditRecorder,
    requests: ChangeRequests,
    resolve: ProjectAccessResolver,
    run_id: RunId,
    idempotency_key: str,
    now: datetime,
) -> RunView:
    run = _load(store, resolve, run_id, Role.EDITOR)
    if run.status == RunStatus.CANCELLED:
        return _view(store, run)
    if run.status in TERMINAL:
        raise RunStateError(f"A {run.status.value} run cannot be cancelled")
    cancelled = replace(
        run, status=RunStatus.CANCELLED, lease=None, revision=run.revision + 1, updated_at=now
    )
    if not store.save_run(cancelled, expected_revision=run.revision):
        raise RunChangedError("The run changed while it was being cancelled. Try again.")
    actor = resolve(run.project_id).actor
    reply = run.mode == "reply"
    if run.mode == "change":
        # Stopping leaves no candidate, so the request ends as failed and can be sent again.
        requests.failed(run.id, "RUN_CANCELLED", now)
    audit.record(
        project_id=run.project_id,
        actor=AuditActor.user(actor),
        type=EventType.RUN_CANCELLED,
        subjects=(Subject(SubjectKind.RUN, run.id),),
        summary="Stopped the agent's reply" if reply else "Stopped the run",
        occurred_at=now,
    )
    store.add_messages(
        [
            event_message(
                run.id,
                run.project_id,
                ConversationEvent.REPLY_CANCELLED if reply else ConversationEvent.RUN_CANCELLED,
                "Stopped the agent's reply."
                if reply
                else "Stopped the run. Answers given so far are kept; start a new run to go on.",
                now,
                author=actor,
            )
        ]
    )
    store.commit()
    return _view(store, cancelled)


@dataclass(frozen=True)
class AnswerQuestion:
    idempotency_key: str
    question_id: QuestionId
    answer: str | None
    """None skips the question; it then stays an explicit open decision."""
    expected_revision: int | None = None
    """The run revision the reviewer saw. Required to change an answer or skip."""


def answer_question(
    store: RunStore,
    audit: AuditRecorder,
    drafts: DraftAnswers,
    resolve: ProjectAccessResolver,
    run_id: RunId,
    command: AnswerQuestion,
    now: datetime,
) -> RunView:
    """Answer or skip a question of the current round, or change an earlier answer or skip.

    A change is allowed until the backlog version that uses the answer is approved: while its
    round is still open, or once the run's draft is saved, which then moves to its next revision
    (ADR 0010). While the agent is using the answers, a change is refused.
    """
    run = _load(store, resolve, run_id, Role.EDITOR)
    access = resolve(run.project_id)
    fingerprint = _fingerprint(
        "answer",
        [str(command.question_id), command.answer or "", str(command.expected_revision)],
    )
    replay = _replay(store, access, command.idempotency_key, "answer", fingerprint)
    if replay is not None:
        return _view(store, replay)
    questions = store.questions(run.id)
    question = next((q for q in questions if q.id == command.question_id), None)
    if question is None:
        raise NotFoundError("Question not found in this run")
    if question.status != QuestionStatus.OPEN:
        return _change_answer(
            store, audit, drafts, access, run, questions, question, command, fingerprint, now
        )
    if command.expected_revision is not None and command.expected_revision != run.revision:
        raise _stale(run)
    if run.status != RunStatus.WAITING_FOR_INPUT:
        raise RunStateError("The run is not waiting for answers")
    current = [q for q in questions if q.round == run.clarification_rounds]

    prefix = "A" if command.answer is not None else "U"
    resolved = replace(
        question,
        status=QuestionStatus.ANSWERED if command.answer is not None else QuestionStatus.SKIPPED,
        answer=command.answer,
        answer_label=_next_label(questions, prefix),
        answered_by=access.actor.user_id,
        answered_at=now,
    )
    round_questions = [resolved if q.id == resolved.id else q for q in current]
    updated = replace(run, revision=run.revision + 1, updated_at=now)
    if all(q.status != QuestionStatus.OPEN for q in round_questions):
        # The round is complete: the answers become the result of the paused tool call.
        updated = replace(
            updated,
            history=(*run.history, answers_turn(run, round_questions)),
            pending_results=(),
            status=RunStatus.RUNNING,
        )
    if not store.save_run(updated, expected_revision=run.revision):
        raise RunChangedError("The run changed while saving the answer. Try again.")
    store.save_questions([resolved])
    _add_receipt(store, access, command.idempotency_key, "answer", run.id, fingerprint, now)
    answered = command.answer is not None
    audit.record(
        project_id=run.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.CLARIFICATION_ANSWERED if answered else EventType.CLARIFICATION_SKIPPED,
        subjects=(Subject(SubjectKind.QUESTION, question.id), Subject(SubjectKind.RUN, run.id)),
        # The answer and the question are source-derived text; the log names neither.
        summary=(
            f"{'Answered' if answered else 'Skipped'} a clarification question "
            f"(round {question.round})"
        ),
        occurred_at=now,
    )
    store.add_messages(
        [
            answer_message(
                run.id,
                run.project_id,
                question.id,
                command.answer,
                access.actor,
                now,
                changed=False,
            )
        ]
    )
    store.commit()
    return _view(store, updated)


def _change_answer(
    store: RunStore,
    audit: AuditRecorder,
    drafts: DraftAnswers,
    access: ProjectAccess,
    run: Run,
    questions: Sequence[Question],
    question: Question,
    command: AnswerQuestion,
    fingerprint: str,
    now: datetime,
) -> RunView:
    if command.expected_revision is None:
        raise RunStateError(
            "This question is already answered or skipped. Send the run's revision to change it"
        )
    if command.expected_revision != run.revision:
        raise _stale(run)
    open_round = (
        run.status == RunStatus.WAITING_FOR_INPUT and question.round == run.clarification_rounds
    )
    version_id = None
    if run.mode == "change" and not open_round:
        raise RunStateError(
            "A change run's answers are fixed once its round closes. Send a new change request "
            "to revise them."
        )
    if open_round:
        # Nothing has read this round's answers yet, so the label can follow the new answer.
        prefix = "A" if command.answer is not None else "U"
        label = question.answer_label
        if label is None or not label.startswith(prefix):
            label = _next_label(questions, prefix)
    elif run.status == RunStatus.READY_FOR_REVIEW:
        if command.answer is None:
            raise RunStateError("An answer the draft uses can be changed, but not skipped")
        try:
            version_id = drafts.change_answer(
                run.id, question.id, command.answer, access.actor.user_id, now
            )
        except VersionNotDraftError as error:
            raise AnswerLockedError(
                "This answer is part of an approved backlog version, so it can no longer change"
            ) from error
        # The draft already cites the answer by its label, so the label stays.
        label = question.answer_label
    elif run.status in ADVANCEABLE:
        raise RunStateError("The agent is using this answer. Change it once the draft is ready")
    else:
        raise RunStateError(f"A {run.status.value} run has no draft that uses this answer")

    changed = replace(
        question,
        status=QuestionStatus.ANSWERED if command.answer is not None else QuestionStatus.SKIPPED,
        answer=command.answer,
        answer_label=label,
        answered_by=access.actor.user_id,
        answered_at=now,
    )
    updated = replace(run, revision=run.revision + 1, updated_at=now)
    if not store.save_run(updated, expected_revision=run.revision):
        raise RunChangedError("The run changed while saving the answer. Try again.")
    store.save_questions([changed])
    _add_receipt(store, access, command.idempotency_key, "answer", run.id, fingerprint, now)
    subjects = [Subject(SubjectKind.QUESTION, question.id), Subject(SubjectKind.RUN, run.id)]
    if version_id is not None:
        subjects.append(Subject(SubjectKind.BACKLOG_VERSION, version_id))
    audit.record(
        project_id=run.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.CLARIFICATION_ANSWER_CHANGED,
        subjects=tuple(subjects),
        summary=(
            f"Changed the answer to a clarification question (round {question.round})"
            + ("; the draft moved to its next revision" if version_id is not None else "")
        ),
        occurred_at=now,
    )
    store.add_messages(
        [
            answer_message(
                run.id, run.project_id, question.id, command.answer, access.actor, now, changed=True
            )
        ]
    )
    store.commit()
    return _view(store, updated)


def _next_label(questions: Sequence[Question], prefix: str) -> str:
    """One past the highest label with the prefix: a changed answer can leave a gap."""
    numbers = [
        int(label[1:])
        for q in questions
        if (label := q.answer_label) is not None
        and label.startswith(prefix)
        and label[1:].isdigit()
    ]
    return f"{prefix}{max(numbers, default=0) + 1}"


def _stale(run: Run) -> RunChangedError:
    return RunChangedError(
        "The run changed since you opened it. Reload it and try again.",
        details={"current_revision": run.revision},
    )


def advance_run(
    store: RunStore,
    audit: AuditRecorder,
    passages: PassageReader,
    candidates: CandidateStore,
    changes: ChangeStore,
    requests: ChangeRequests,
    record_people: PeopleRecorder,
    context: ProjectContext,
    runtime: AgentRuntime,
    resolve: ProjectAccessResolver,
    run_id: RunId,
    idempotency_key: str,
    clock: Callable[[], datetime],
) -> RunView:
    """Execute one bounded step. A run that cannot advance (waiting or finished) is returned as is.

    Retrying with the same Idempotency-Key returns the run's current state without another step.
    """
    now = clock()
    run = _load(store, resolve, run_id, Role.EDITOR)
    access = resolve(run.project_id)
    fingerprint = _fingerprint("advance", [str(run.id)])
    replay = _replay(store, access, idempotency_key, "advance", fingerprint)
    if replay is not None:
        return _view(store, replay)
    if run.status not in ADVANCEABLE:
        return _view(store, run)
    if runtime.primary is None:
        raise ModelNotConfiguredError("No model provider is configured (MODEL_PROVIDER)")
    pinned_model = (run.inputs.provider, run.inputs.model_id)
    served = runtime.served(pinned_model)
    if served is None:
        raise RunModelChangedError(
            f"This run was created with {' '.join(pinned_model)}, which the API no longer "
            "serves. Switch back or start a new run."
        )
    if run.lease_is_active(now):
        raise RunBusyError("Another request is running a step of this run. Try again shortly.")

    pinned = passages.load(run.project_id, run.inputs.source_version_ids)
    reply = _reply_input(store, context, run) if run.mode == "reply" else None
    change = _change_input(context, run) if run.mode == "change" else None
    questions = (
        store.answered_questions(run.project_id) if reply is not None else store.questions(run.id)
    )
    project_spent = store.project_cost_microusd(run.project_id)
    leased = replace(
        run,
        status=RunStatus.RUNNING,
        lease=Lease(new_id(), now + timedelta(seconds=runtime.lease_seconds)),
        revision=run.revision + 1,
        updated_at=now,
    )
    if not store.save_run(leased, expected_revision=run.revision):
        raise RunChangedError("Another request advanced the run first. Try again.")
    _add_receipt(store, access, idempotency_key, "advance", run.id, fingerprint, now)
    store.commit()

    # No transaction is open from here until the outcome is saved.
    step_context = StepContext(
        provider=served.provider,
        passages=pinned,
        questions=questions,
        project_spent_microusd=project_spent,
        project_limit_microusd=runtime.project_cost_limit_microusd,
        now=now,
        new_id=new_id,
    )
    if reply is not None:
        outcome = take_reply_step(leased, step_context, reply)
    else:
        outcome = take_step(leased, step_context, change)

    outcome = _apply_fallback_policy(outcome, served, runtime, clock())
    outcome = _refuse_unsound_candidate(outcome, candidates, clock())
    outcome = _refuse_unsound_change(outcome, changes, clock())
    finished = replace(outcome.run, lease=None, revision=leased.revision + 1, updated_at=clock())
    if not store.save_run(finished, expected_revision=leased.revision):
        store.add_usage(finished, since=leased)
        store.add_steps(_discarded(outcome.steps))
        store.commit()
        raise RunChangedError(
            "The run was cancelled or taken over while this step ran; its result was discarded"
        )
    store.add_steps(outcome.steps)
    store.save_questions(outcome.questions)
    messages = _step_messages(finished, outcome, pinned, step_context.questions)
    store.add_messages(messages)
    if outcome.change is not None:
        _record_change(audit, changes, requests, finished, outcome.change, messages)
    elif finished.mode == "change" and finished.status == RunStatus.FAILED:
        requests.failed(finished.id, finished.error.code if finished.error else "FAILED", now)
    replied = next((m for m in messages if m.kind == MessageKind.REPLY), None)
    if replied is not None and outcome.suggestion is not None:
        store.add_suggestion(
            Suggestion(
                message_id=replied.id,
                project_id=replied.project_id,
                proposed=outcome.suggestion,
                created_at=replied.created_at,
            )
        )
    if replied is not None:
        cited = sum(1 for claim in replied.claims if claim.basis == "cited")
        claims = len(replied.claims)
        audit.record(
            project_id=finished.project_id,
            actor=AuditActor.agent(),
            type=EventType.MESSAGE_REPLIED,
            subjects=(Subject(SubjectKind.MESSAGE, replied.id), Subject(SubjectKind.RUN, run.id)),
            summary=f"Replied with {claims} {'claim' if claims == 1 else 'claims'}, {cited} cited",
            occurred_at=finished.updated_at,
        )
    if outcome.questions:
        asked = len(outcome.questions)
        audit.record(
            project_id=finished.project_id,
            actor=AuditActor.agent(),
            type=EventType.CLARIFICATION_REQUESTED,
            subjects=(
                Subject(SubjectKind.RUN, finished.id),
                *(Subject(SubjectKind.QUESTION, q.id) for q in outcome.questions),
            ),
            summary=(
                f"Asked {asked} clarification {'question' if asked == 1 else 'questions'} "
                f"(round {finished.clarification_rounds})"
            ),
            occurred_at=finished.updated_at,
        )
    if finished.status == RunStatus.FAILED and finished.error is not None:
        audit.record(
            project_id=finished.project_id,
            actor=AuditActor.agent(),
            type=EventType.RUN_FAILED,
            subjects=(Subject(SubjectKind.RUN, finished.id),),
            summary=f"{_FAILED[finished.mode]} ({finished.error.code})",
            occurred_at=finished.updated_at,
        )
    if outcome.candidate is not None:
        candidates.save(outcome.candidate, finished.updated_at)
        # Only with a saved candidate: a refused draft leaves no people behind either.
        record_people(finished.project_id, finished.id, outcome.people, finished.updated_at)
    store.commit()
    return _view(store, finished)


# What a failed run was doing, for the activity log; the error code says why.
_FAILED = {
    "initial": "The run failed",
    "change": "The change analysis failed",
    "reply": "The reply failed",
}

# Earlier messages are read in one page; the reply keeps the free messages and replies in it.
_CONTEXT_PAGE = 30


def _reply_input(store: RunStore, context: ProjectContext, run: Run) -> ReplyInput:
    message = next((m for m in store.run_messages(run.id) if m.kind == MessageKind.MESSAGE), None)
    if message is None:
        raise RunStateError("This reply run has no message to answer")
    before = store.newest_messages(
        run.project_id, before=MessageCursor(message.created_at, message.id), limit=_CONTEXT_PAGE
    )
    earlier = earlier_messages(list(reversed(before)))
    return ReplyInput(
        message=message,
        earlier=earlier,
        backlog=context.backlog(run.project_id),
        has_baseline=context.has_baseline(run.project_id),
        suggestions=store.suggestions_for([m.id for m in earlier if m.kind == MessageKind.REPLY]),
    )


def _change_input(context: ProjectContext, run: Run) -> ChangeInput:
    """The baseline the run was pinned to, under the labels the model sees. An approved version
    never changes, and the hash pinned with the request proves it."""
    change = run.inputs.change
    base = None if change is None else context.version(change.base_version_id)
    if change is None or base is None or base.content_hash != change.base_content_hash:
        raise RunStateError("This change run's baseline is not available")
    current = context.baseline(run.project_id)
    number = current.number if current is not None and current.version.id == base.id else 0
    return ChangeInput(baseline_labels(base, number))


def _step_messages(
    run: Run, outcome: StepOutcome, pinned: Sequence[Passage], questions: Sequence[Question]
) -> list[Message]:
    """What a committed step adds to the conversation. A transient error adds nothing: the run
    stays advanceable."""
    now = run.updated_at
    if outcome.change is not None:
        blocks = analysis_blocks(source_blocks(pinned, request_version(run)), pinned, questions)
        claims = resolve_claims(outcome.change.claims_output, blocks)
        ready = outcome.change.proposal is not None
        return [
            reply_message(run.id, run.project_id, claims, now, kind=MessageKind.ANALYSIS),
            event_message(
                run.id,
                run.project_id,
                ConversationEvent.CHANGE_READY if ready else ConversationEvent.CHANGE_NOT_NEEDED,
                "The proposed change is ready for review."
                if ready
                else "No change is needed: the baseline already covers this request.",
                now,
            ),
        ]
    if run.mode == "reply":
        if outcome.claims:
            return [reply_message(run.id, run.project_id, outcome.claims, now)]
        if run.status == RunStatus.FAILED and run.error is not None:
            event = ConversationEvent.REPLY_FAILED
            return [event_message(run.id, run.project_id, event, run.error.message, now)]
        return []
    messages = [
        question_message(run.id, run.project_id, q.id, q.text, now) for q in outcome.questions
    ]
    if run.status == RunStatus.READY_FOR_REVIEW:
        text = "The draft backlog is ready for review."
        messages.append(
            event_message(run.id, run.project_id, ConversationEvent.RUN_READY, text, now)
        )
    elif run.status == RunStatus.FAILED and run.error is not None:
        event = ConversationEvent.RUN_FAILED
        messages.append(event_message(run.id, run.project_id, event, run.error.message, now))
    return messages


def _refuse_unsound_candidate(
    outcome: StepOutcome, candidates: CandidateStore, now: datetime
) -> StepOutcome:
    """Fail the run instead of saving a candidate the backlog module would refuse: one whose
    ids, hierarchy, limits or evidence do not hold up against what is stored."""
    if outcome.candidate is None:
        return outcome
    problems = candidates.problems(outcome.candidate)
    if not problems:
        return outcome
    run = outcome.run
    refused = RunStep(
        id=StepId(new_id()),
        run_id=run.id,
        kind="event",
        name="candidate_refused",
        stage=run.stage,
        created_at=now,
        detail={"problems": len(problems)},
    )
    failed = replace(
        run,
        status=RunStatus.FAILED,
        problems=tuple(problems[:MAX_REPORTED]),
        error=RunError(
            "CANDIDATE_REFUSED",
            "The draft did not pass validation, so no backlog was saved. Start a new run.",
            retryable=False,
        ),
    )
    return replace(outcome, run=failed, steps=(*outcome.steps, refused), candidate=None, people=())


def _refuse_unsound_change(
    outcome: StepOutcome, changes: ChangeStore, now: datetime
) -> StepOutcome:
    """Fail the run instead of saving a change the backlog module would refuse, for example one
    made against a baseline that is no longer current."""
    proposal = None if outcome.change is None else outcome.change.proposal
    if proposal is None:
        return outcome
    problems = changes.problems(proposal)
    if not problems:
        return outcome
    run = outcome.run
    refused = RunStep(
        id=StepId(new_id()),
        run_id=run.id,
        kind="event",
        name="change_refused",
        stage=run.stage,
        created_at=now,
        detail={"problems": len(problems)},
    )
    failed = replace(
        run,
        status=RunStatus.FAILED,
        problems=tuple(problems[:MAX_REPORTED]),
        error=RunError(
            "CHANGE_REFUSED",
            "The proposed change did not pass validation, so nothing was proposed. Reload the "
            "baseline and send the request again.",
            retryable=False,
        ),
    )
    return replace(outcome, run=failed, steps=(*outcome.steps, refused), change=None)


def _record_change(
    audit: AuditRecorder,
    changes: ChangeStore,
    requests: ChangeRequests,
    run: Run,
    result: ChangeResult,
    messages: Sequence[Message],
) -> None:
    """Save the candidate, if any, and record the analysis on the change request, in the step's
    transaction. The baseline is only read."""
    now = run.updated_at
    saved = None if result.proposal is None else changes.save(result.proposal, now)

    def item_id(ref: ItemRef) -> ItemId | None:
        if isinstance(ref, str):
            return None if saved is None else saved.item_ids.get(ref)
        return ref

    rationales = tuple(
        ItemNote(found, note) for ref, note in result.rationales if (found := item_id(ref))
    )
    reversals = tuple(
        ScopeReversal(
            decision_id=saved.decision_ids[r.key],
            reverses=r.reverses,
            summary=r.summary,
            reversed_decision_id=None
            if r.reversed_decision_id is None
            else DecisionId(r.reversed_decision_id),
        )
        for r in result.reversals
        if saved is not None and r.key in saved.decision_ids
    )
    summary = requests.analyzed(
        run.id,
        ChangeAnalysis(
            candidate_version_id=None if saved is None else saved.version_id,
            analysis=result.analysis,
            rationales=rationales,
            impacts=tuple(ItemNote(i, note) for i, note in result.impacts),
            scope_reversals=reversals,
        ),
        now,
    )
    analysis = next((m for m in messages if m.kind == MessageKind.ANALYSIS), None)
    change_request = run.inputs.change
    subjects = [Subject(SubjectKind.RUN, run.id)]
    if change_request is not None:
        subjects.insert(0, Subject(SubjectKind.CHANGE_REQUEST, change_request.change_request_id))
    if saved is not None:
        subjects.append(Subject(SubjectKind.BACKLOG_VERSION, saved.version_id))
    if analysis is not None:
        subjects.append(Subject(SubjectKind.MESSAGE, analysis.id))
    audit.record(
        project_id=run.project_id,
        actor=AuditActor.agent(),
        type=EventType.CHANGE_ANALYZED,
        subjects=tuple(subjects),
        summary=(
            "Found no change needed: the baseline already covers the request"
            if summary is None
            else f"Proposed a change: {summary.added} added, {summary.changed} changed, "
            f"{summary.removed} removed, {len(reversals)} scope "
            f"{'decision' if len(reversals) == 1 else 'decisions'} needed"
        ),
        occurred_at=now,
    )


def _apply_fallback_policy(
    outcome: StepOutcome, served: ServedModel, runtime: AgentRuntime, now: datetime
) -> StepOutcome:
    """Feed the circuit breaker, and move a run that has not had one successful call to the
    backup when the primary is unavailable. The next advance then runs on the backup."""
    run = outcome.run
    if served != runtime.primary:
        return outcome
    unavailable = run.error is not None and run.error.code in AVAILABILITY_ERRORS
    if not unavailable:
        if run.counters.total_tokens > 0:
            runtime.breaker.record_success()
        return outcome
    runtime.breaker.record_failure()
    fallback = runtime.fallback
    if fallback is None or run.counters.total_tokens > 0 or run.history:
        return outcome
    event = RunStep(
        id=StepId(new_id()),
        run_id=run.id,
        kind="event",
        name="fallback",
        stage=run.stage,
        created_at=now,
        provider=fallback.provider_name,
        model_id=fallback.model_id,
        detail={
            "from_provider": served.provider_name,
            "from_model": served.model_id,
            "reason": run.error.code if run.error else "",
        },
    )
    moved = replace(
        run,
        inputs=replace(
            run.inputs,
            provider=fallback.provider_name,
            model_id=fallback.model_id,
            fallback_reason=f"primary_{run.error.code.lower() if run.error else 'unavailable'}",
        ),
        error=None,
    )
    return replace(outcome, run=moved, steps=(*outcome.steps, event))


def _discarded(steps: Sequence[RunStep]) -> list[RunStep]:
    return [replace(step, detail={**step.detail, "discarded": True}) for step in steps]


def _load(store: RunStore, resolve: ProjectAccessResolver, run_id: RunId, role: Role) -> Run:
    run = store.get_run(run_id)
    if run is None:
        raise NotFoundError("Run not found")
    access = resolve(run.project_id)
    # A run in a project the actor cannot see is reported exactly like a missing one.
    access.require_member()
    if role != Role.VIEWER:
        access.require_role(role)
    return run


def _view(store: RunStore, run: Run) -> RunView:
    return RunView(
        run=run,
        questions=tuple(store.questions(run.id)),
        project_cost_microusd=store.project_cost_microusd(run.project_id),
    )


def _fingerprint(operation: str, parts: Sequence[str]) -> str:
    return hashlib.sha256(json.dumps([operation, *parts]).encode()).hexdigest()


def _replay(
    store: RunStore, access: ProjectAccess, key: str, operation: str, fingerprint: str
) -> Run | None:
    receipt = store.find_receipt(access.actor.user_id, key)
    if receipt is None:
        return None
    if receipt.operation != operation or receipt.fingerprint != fingerprint:
        raise IdempotencyKeyReusedError("This Idempotency-Key was already used for another request")
    return store.get_run(receipt.run_id)


def _add_receipt(
    store: RunStore,
    access: ProjectAccess,
    key: str,
    operation: str,
    run_id: RunId,
    fingerprint: str,
    now: datetime,
) -> None:
    store.add_receipt(
        Receipt(
            actor_id=access.actor.user_id,
            idempotency_key=key,
            operation=operation,
            run_id=run_id,
            fingerprint=fingerprint,
            created_at=now,
        )
    )
