"""Drive an agent run to its end, or reply to one message, in memory, for evaluation.

It takes the same bounded steps as the API (`take_step`, `take_reply_step`) and resolves
clarification rounds the way `answer_question` does, but keeps the run in memory: no database,
leases or receipts.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from scopesteps.agent.application.ports import ModelProvider, Passage
from scopesteps.agent.application.replying import REPLY_PROMPT_VERSION, REPLY_SCHEMA_VERSION
from scopesteps.agent.application.steps import (
    AGENT_EXPLORE,
    AGENT_SCHEMA_VERSION,
    ExploreName,
    ReplyInput,
    StepContext,
    agent_prompt_version,
    answers_turn,
    take_reply_step,
    take_step,
)
from scopesteps.agent.domain.budget import RunLimits
from scopesteps.agent.domain.conversation import Claim, Message, MessageKind, MessageRole
from scopesteps.agent.domain.ids import MessageId, QuestionId, RunId
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
    explore: ExploreName = AGENT_EXPLORE,
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
            prompt_version=agent_prompt_version(explore),
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
                explore=explore,
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


@dataclass(frozen=True)
class RecordedAnswer:
    """A clarification answer the project already holds, citable in a reply as A1, A2, ..."""

    question: str
    answer: str


@dataclass(frozen=True)
class OfflineReply:
    run: Run
    steps: tuple[RunStep, ...]
    claims: tuple[Claim, ...]
    """The reply as it would be stored: citations resolved in code, the rest the agent's own."""
    answer_ids: tuple[QuestionId, ...]
    """The id a citation of each recorded answer carries, in the order the answers were given."""


def reply_offline(
    provider: ModelProvider,
    passages: Sequence[Passage],
    answers: Sequence[RecordedAnswer],
    message: str,
    *,
    provider_name: str,
    model_id: str,
    limits: RunLimits,
) -> OfflineReply:
    """Reply to one message with the same step a reply run takes, with no backlog and no earlier
    conversation. The message is used as given: the caller keeps it within the message limit."""
    now = datetime.now(UTC)
    project_id = ProjectId(uuid4())
    run = Run(
        id=RunId(uuid4()),
        project_id=project_id,
        mode="reply",
        status=RunStatus.RUNNING,
        stage=RunStage.REPLY,
        revision=1,
        inputs=RunInputs(
            source_version_ids=tuple(sorted({p.source_version_id for p in passages}, key=str)),
            provider=provider_name,
            model_id=model_id,
            prompt_version=REPLY_PROMPT_VERSION,
            schema_version=REPLY_SCHEMA_VERSION,
            limits=limits,
            max_clarification_rounds=0,
        ),
        created_by=UserId(uuid4()),
        created_at=now,
        updated_at=now,
    )
    questions = [
        Question(
            id=QuestionId(uuid4()),
            run_id=RunId(uuid4()),
            round=1,
            call_id="recorded",
            subject=recorded.question,
            text=recorded.question,
            why_it_matters="",
            block_labels=(),
            status=QuestionStatus.ANSWERED,
            answer=recorded.answer,
            answer_label=f"A{index}",
        )
        for index, recorded in enumerate(answers, start=1)
    ]
    sent = Message(
        id=MessageId(uuid4()),
        project_id=project_id,
        role=MessageRole.USER,
        kind=MessageKind.MESSAGE,
        text=message,
        created_at=now,
        run_id=run.id,
    )
    outcome = take_reply_step(
        run,
        StepContext(
            provider=provider,
            passages=passages,
            questions=questions,
            project_spent_microusd=0,
            project_limit_microusd=None,
            now=now,
            new_id=_new_id,
        ),
        ReplyInput(message=sent, earlier=(), backlog=None),
    )
    return OfflineReply(outcome.run, outcome.steps, outcome.claims, tuple(q.id for q in questions))


def _new_id() -> UUID:
    return uuid4()
