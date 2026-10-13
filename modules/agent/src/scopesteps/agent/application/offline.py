"""Drive an agent run to its end in memory, for evaluation.

It takes the same bounded steps as the API (`take_step`) and resolves clarification rounds the way
`answer_question` does, but keeps the run in memory: no database, leases or receipts.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from scopesteps.agent.application.ports import ModelProvider, Passage
from scopesteps.agent.application.steps import (
    AGENT_PROMPT_VERSION,
    AGENT_SCHEMA_VERSION,
    StepContext,
    answers_turn,
    take_step,
)
from scopesteps.agent.domain.budget import RunLimits
from scopesteps.agent.domain.ids import RunId
from scopesteps.agent.domain.run import (
    ADVANCEABLE,
    Question,
    QuestionStatus,
    Run,
    RunInputs,
    RunStage,
    RunStatus,
    RunStep,
)
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId

Answerer = Callable[[Question], str | None]
"""The reviewer: returns an answer for a question, or None to skip it."""


@dataclass(frozen=True)
class OfflineRun:
    run: Run
    questions: tuple[Question, ...]
    steps: tuple[RunStep, ...]


def run_offline(
    provider: ModelProvider,
    passages: Sequence[Passage],
    *,
    provider_name: str,
    model_id: str,
    limits: RunLimits,
    max_clarification_rounds: int,
    answer: Answerer,
    before_step: Callable[[], None] = lambda: None,
    on_transient: Callable[[int], bool] = lambda failures: False,
    max_steps: int = 20,
) -> OfflineRun:
    """Advance a new initial run until it is ready, failed, or out of steps.

    `before_step` runs before every step (for pacing). A transient provider error leaves the run
    advanceable; `on_transient(failures)` decides whether to try that step again.
    """
    now = datetime.now(UTC)
    run = Run(
        id=RunId(uuid4()),
        project_id=ProjectId(uuid4()),
        mode="initial",
        status=RunStatus.CREATED,
        stage=RunStage.EXPLORE,
        revision=1,
        inputs=RunInputs(
            source_version_ids=tuple(sorted({p.source_version_id for p in passages}, key=str)),
            provider=provider_name,
            model_id=model_id,
            prompt_version=AGENT_PROMPT_VERSION,
            schema_version=AGENT_SCHEMA_VERSION,
            limits=limits,
            max_clarification_rounds=max_clarification_rounds,
        ),
        created_by=UserId(uuid4()),
        created_at=now,
        updated_at=now,
    )
    questions: list[Question] = []
    steps: list[RunStep] = []
    failures = 0
    for _ in range(max_steps):
        if run.status == RunStatus.WAITING_FOR_INPUT:
            run, questions = _answer_round(run, questions, answer)
            continue
        if run.status not in ADVANCEABLE:
            break
        before_step()
        outcome = take_step(
            replace(run, status=RunStatus.RUNNING),
            StepContext(
                provider=provider,
                passages=passages,
                questions=tuple(questions),
                project_spent_microusd=0,
                project_limit_microusd=None,
                now=datetime.now(UTC),
                new_id=_new_id,
            ),
        )
        run = outcome.run
        steps.extend(outcome.steps)
        questions.extend(outcome.questions)
        if run.error is not None and run.error.retryable and run.status in ADVANCEABLE:
            failures += 1
            if not on_transient(failures):
                break
    return OfflineRun(run, tuple(questions), tuple(steps))


def _answer_round(
    run: Run, questions: list[Question], answer: Answerer
) -> tuple[Run, list[Question]]:
    """Resolve every open question of the current round, labelling answers A1.. and skips U1..."""
    resolved_all = list(questions)
    current = [q for q in questions if q.round == run.clarification_rounds]
    for question in current:
        if question.status != QuestionStatus.OPEN:
            continue
        text = answer(question)
        prefix = "A" if text is not None else "U"
        used = sum(1 for q in resolved_all if (q.answer_label or "").startswith(prefix))
        resolved = replace(
            question,
            status=QuestionStatus.ANSWERED if text is not None else QuestionStatus.SKIPPED,
            answer=text,
            answer_label=f"{prefix}{used + 1}",
        )
        resolved_all = [resolved if q.id == question.id else q for q in resolved_all]
    round_questions = [q for q in resolved_all if q.round == run.clarification_rounds]
    resumed = replace(
        run,
        history=(*run.history, answers_turn(run, round_questions)),
        pending_results=(),
        status=RunStatus.RUNNING,
    )
    return resumed, resolved_all


def _new_id() -> UUID:
    return uuid4()
