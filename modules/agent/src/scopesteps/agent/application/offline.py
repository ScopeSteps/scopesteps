"""Drive an agent run to its end, analyse a change request, or reply to one message, in memory,
for evaluation.

It takes the same bounded steps as the API (`take_step`, `take_reply_step`) and resolves
clarification rounds the way `answer_question` does, but keeps the run in memory: no database,
leases or receipts.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from scopesteps.agent.application.changing import (
    CHANGE_PROMPT_VERSION,
    CHANGE_REQUEST_KIND,
    CHANGE_SCHEMA_VERSION,
    BaselineLabels,
    ChangeResult,
    baseline_labels,
)
from scopesteps.agent.application.ports import ModelProvider, Passage
from scopesteps.agent.application.replying import (
    CONVERSATION_REPLY,
    REPLY_SCHEMAS,
    ReplyName,
    reply_prompt_version,
)
from scopesteps.agent.application.steps import (
    AGENT_EXPLORE,
    AGENT_SCHEMA_VERSION,
    ChangeInput,
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
    ChangeInputs,
    Question,
    QuestionStatus,
    Run,
    RunInputs,
    RunStage,
    RunStatus,
    RunStep,
)
from scopesteps.agent.domain.suggestion import ProposedSuggestion
from scopesteps.backlog.client import BacklogOutline, BacklogVersion
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
    return _drive(
        run,
        provider,
        passages,
        answer=answer,
        before_step=before_step,
        on_transient=on_transient,
        max_steps=max_steps,
        explore=explore,
    )


@dataclass(frozen=True)
class OfflineChange:
    run: Run
    questions: tuple[Question, ...]
    steps: tuple[RunStep, ...]
    labels: BaselineLabels
    """The labels the model saw the baseline under."""
    change: ChangeResult | None
    """What the finished analysis proposes; None if it failed or ran out of steps."""


def analyze_change_offline(
    provider: ModelProvider,
    passages: Sequence[Passage],
    baseline: BacklogVersion,
    *,
    provider_name: str,
    model_id: str,
    limits: RunLimits,
    max_clarification_rounds: int,
    answer: Answerer,
    before_step: Callable[[], None] = lambda: None,
    on_transient: Callable[[int], bool] = lambda failures: False,
    max_steps: int = 20,
) -> OfflineChange:
    """Analyse a change request against `baseline` with the steps a change run takes.

    `passages` are the baseline's sources followed by the request's paragraphs, whose
    `source_kind` is `change_request`, exactly as a change run pins them.
    """
    request = next((p for p in passages if p.source_kind == CHANGE_REQUEST_KIND), None)
    if request is None:
        raise ValueError("The passages hold no change request")
    now = datetime.now(UTC)
    run = Run(
        id=RunId(uuid4()),
        project_id=baseline.project_id,
        mode="change",
        status=RunStatus.CREATED,
        stage=RunStage.EXPLORE,
        revision=1,
        inputs=RunInputs(
            source_version_ids=tuple(dict.fromkeys(p.source_version_id for p in passages)),
            provider=provider_name,
            model_id=model_id,
            prompt_version=CHANGE_PROMPT_VERSION,
            schema_version=CHANGE_SCHEMA_VERSION,
            limits=limits,
            max_clarification_rounds=max_clarification_rounds,
            change=ChangeInputs(
                change_request_id=uuid4(),
                base_version_id=baseline.id,
                base_content_hash=baseline.content_hash,
                request_version_id=request.source_version_id,
            ),
        ),
        created_by=UserId(uuid4()),
        created_at=now,
        updated_at=now,
    )
    labels = baseline_labels(baseline, 1)
    driven = _drive(
        run,
        provider,
        passages,
        answer=answer,
        before_step=before_step,
        on_transient=on_transient,
        max_steps=max_steps,
        change=ChangeInput(labels),
    )
    return OfflineChange(driven.run, driven.questions, driven.steps, labels, driven.change_result)


@dataclass(frozen=True)
class _Driven(OfflineRun):
    change_result: ChangeResult | None = None


def _drive(
    run: Run,
    provider: ModelProvider,
    passages: Sequence[Passage],
    *,
    answer: Answerer,
    before_step: Callable[[], None],
    on_transient: Callable[[int], bool],
    max_steps: int,
    explore: ExploreName = AGENT_EXPLORE,
    change: ChangeInput | None = None,
) -> _Driven:
    questions: list[Question] = []
    steps: list[RunStep] = []
    change_result: ChangeResult | None = None
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
            change,
        )
        run = outcome.run
        steps.extend(outcome.steps)
        questions.extend(outcome.questions)
        change_result = outcome.change or change_result
        if run.error is not None and run.error.retryable and run.status in ADVANCEABLE:
            failures += 1
            if not on_transient(failures):
                break
    return _Driven(run, tuple(questions), tuple(steps), change_result)


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
    suggestion: ProposedSuggestion | None = None
    """reply-v3: the suggested next step that passed the checks, as it would be stored."""


@dataclass(frozen=True)
class EarlierMessage:
    """A message or reply sent before the one being answered, for a multi-turn evaluation."""

    role: Literal["user", "agent"]
    text: str


# A reply-v2 reply ends within MAX_LOOKUPS + 1 calls; one more step allows for its retry.
_MAX_REPLY_STEPS = 6


def reply_offline(
    provider: ModelProvider,
    passages: Sequence[Passage],
    answers: Sequence[RecordedAnswer],
    message: str,
    *,
    provider_name: str,
    model_id: str,
    limits: RunLimits,
    prompt: ReplyName = CONVERSATION_REPLY,
    earlier: Sequence[EarlierMessage] = (),
    backlog: BacklogOutline | None = None,
    has_baseline: bool = False,
    before_step: Callable[[], None] | None = None,
) -> OfflineReply:
    """Reply to one message with the same steps a reply run takes, advancing until the reply is
    stored, fails or meets a transient error (left `running`, as a run would be). The message is
    used as given: the caller keeps it within the message limit. `before_step` runs before each
    step, for pacing."""
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
            prompt_version=reply_prompt_version(prompt),
            schema_version=REPLY_SCHEMAS[prompt],
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
    before = tuple(
        Message(
            id=MessageId(uuid4()),
            project_id=project_id,
            role=MessageRole(m.role),
            kind=MessageKind.MESSAGE if m.role == "user" else MessageKind.REPLY,
            text=m.text,
            created_at=now,
        )
        for m in earlier
    )
    context = StepContext(
        provider=provider,
        passages=passages,
        questions=questions,
        project_spent_microusd=0,
        project_limit_microusd=None,
        now=now,
        new_id=_new_id,
    )
    steps: list[RunStep] = []
    claims: tuple[Claim, ...] = ()
    suggestion: ProposedSuggestion | None = None
    for _ in range(_MAX_REPLY_STEPS):
        if before_step is not None:
            before_step()
        outcome = take_reply_step(
            run, context, ReplyInput(sent, before, backlog, has_baseline=has_baseline)
        )
        run, claims, suggestion = outcome.run, outcome.claims, outcome.suggestion
        steps.extend(outcome.steps)
        if run.status != RunStatus.RUNNING or run.error is not None:
            break
    return OfflineReply(run, tuple(steps), claims, tuple(q.id for q in questions), suggestion)


def _new_id() -> UUID:
    return uuid4()
