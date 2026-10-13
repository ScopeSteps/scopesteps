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
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

from scopesteps.agent.application.ports import ModelProvider, PassageReader, Receipt, RunStore
from scopesteps.agent.application.steps import (
    AGENT_PROMPT_VERSION,
    AGENT_SCHEMA_VERSION,
    StepContext,
    answers_turn,
    take_step,
)
from scopesteps.agent.domain.budget import RunLimits
from scopesteps.agent.domain.ids import QuestionId, RunId
from scopesteps.agent.domain.run import (
    ADVANCEABLE,
    TERMINAL,
    Lease,
    Question,
    QuestionStatus,
    Run,
    RunBusyError,
    RunChangedError,
    RunInputs,
    RunStage,
    RunStateError,
    RunStatus,
    RunStep,
)
from scopesteps.identity.client import ProjectAccess, ProjectAccessResolver, Role
from scopesteps.kernel.errors import (
    ConflictError,
    FeatureNotImplementedError,
    NotFoundError,
    UnavailableError,
)
from scopesteps.kernel.ids import new_id
from scopesteps.sources.client import SourceVersionId


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
    """What the composition root provides: one configured provider and the limits new runs pin."""

    provider: ModelProvider | None
    provider_name: str
    model_id: str
    limits: RunLimits
    max_clarification_rounds: int
    project_cost_limit_microusd: int | None
    lease_seconds: float


@dataclass(frozen=True)
class RunView:
    run: Run
    questions: tuple[Question, ...]
    project_cost_microusd: int


@dataclass(frozen=True)
class CreateRun:
    idempotency_key: str
    mode: Literal["initial", "change"]
    source_version_ids: tuple[SourceVersionId, ...]


def create_run(
    store: RunStore,
    passages: PassageReader,
    runtime: AgentRuntime,
    access: ProjectAccess,
    command: CreateRun,
    now: datetime,
) -> RunView:
    access.require_role(Role.EDITOR)
    if command.mode == "change":
        raise FeatureNotImplementedError("Change runs")
    fingerprint = _fingerprint("create", [str(v) for v in command.source_version_ids])
    replay = _replay(store, access, command.idempotency_key, "create", fingerprint)
    if replay is not None:
        return _view(store, replay)
    if runtime.provider is None:
        raise ModelNotConfiguredError("No model provider is configured (MODEL_PROVIDER)")
    if not passages.load(access.project_id, command.source_version_ids):
        raise NotFoundError("The selected sources have no paragraphs")
    run = Run(
        id=RunId(new_id()),
        project_id=access.project_id,
        mode="initial",
        status=RunStatus.CREATED,
        stage=RunStage.EXPLORE,
        revision=1,
        inputs=RunInputs(
            source_version_ids=command.source_version_ids,
            provider=runtime.provider_name,
            model_id=runtime.model_id,
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
    store.commit()
    return _view(store, run)


def get_run(store: RunStore, resolve: ProjectAccessResolver, run_id: RunId) -> RunView:
    run = _load(store, resolve, run_id, Role.VIEWER)
    return _view(store, run)


def cancel_run(
    store: RunStore,
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
    store.commit()
    return _view(store, cancelled)


@dataclass(frozen=True)
class AnswerQuestion:
    idempotency_key: str
    question_id: QuestionId
    answer: str | None
    """None skips the question; it then stays an explicit open decision."""


def answer_question(
    store: RunStore,
    resolve: ProjectAccessResolver,
    run_id: RunId,
    command: AnswerQuestion,
    now: datetime,
) -> RunView:
    run = _load(store, resolve, run_id, Role.EDITOR)
    access = resolve(run.project_id)
    fingerprint = _fingerprint("answer", [str(command.question_id), command.answer or ""])
    replay = _replay(store, access, command.idempotency_key, "answer", fingerprint)
    if replay is not None:
        return _view(store, replay)
    if run.status != RunStatus.WAITING_FOR_INPUT:
        raise RunStateError("The run is not waiting for answers")
    questions = store.questions(run.id)
    current = [q for q in questions if q.round == run.clarification_rounds]
    question = next((q for q in current if q.id == command.question_id), None)
    if question is None:
        raise NotFoundError("Question not found in the current clarification round")
    if question.status != QuestionStatus.OPEN:
        raise RunStateError("This question is already answered or skipped")

    prefix = "A" if command.answer is not None else "U"
    used = sum(1 for q in questions if (q.answer_label or "").startswith(prefix))
    resolved = replace(
        question,
        status=QuestionStatus.ANSWERED if command.answer is not None else QuestionStatus.SKIPPED,
        answer=command.answer,
        answer_label=f"{prefix}{used + 1}",
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
    store.commit()
    return _view(store, updated)


def advance_run(
    store: RunStore,
    passages: PassageReader,
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
    if runtime.provider is None:
        raise ModelNotConfiguredError("No model provider is configured (MODEL_PROVIDER)")
    pinned_model = (run.inputs.provider, run.inputs.model_id)
    if pinned_model != (runtime.provider_name, runtime.model_id):
        raise RunModelChangedError(
            f"This run was created with {' '.join(pinned_model)}; the API now serves "
            f"{runtime.provider_name} {runtime.model_id}. Switch back or start a new run."
        )
    if run.lease_is_active(now):
        raise RunBusyError("Another request is running a step of this run. Try again shortly.")

    pinned = passages.load(run.project_id, run.inputs.source_version_ids)
    questions = store.questions(run.id)
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
    outcome = take_step(
        leased,
        StepContext(
            provider=runtime.provider,
            passages=pinned,
            questions=questions,
            project_spent_microusd=project_spent,
            project_limit_microusd=runtime.project_cost_limit_microusd,
            now=now,
            new_id=new_id,
        ),
    )

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
    store.commit()
    return _view(store, finished)


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
