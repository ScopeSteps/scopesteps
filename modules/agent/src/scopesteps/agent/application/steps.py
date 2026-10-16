"""One bounded step of an agent run: one exploring model call, or the draft with its single repair.

A step touches no database, so the caller runs it outside any transaction and commits the outcome
only if the run has not changed meanwhile.
"""

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ValidationError

from scopesteps.agent.application.candidate import to_people, to_proposal
from scopesteps.agent.application.changing import (
    CHANGE_EXPLORE_PROMPT,
    CHANGE_EXPLORE_VERSION,
    CHANGE_PROMPT,
    CHANGE_REQUEST_KIND,
    CHANGE_SCHEMA_VERSION,
    CHANGE_STEP_VERSION,
    CHANGE_TASK,
    REPAIR_INSTRUCTION,
    BaselineLabels,
    ChangeResult,
    ChangeSetOutput,
    change_message,
    change_schema,
    find_change_problems,
    to_change_proposal,
)
from scopesteps.agent.application.changing import EXPLORE_TASK as CHANGE_EXPLORE_TASK
from scopesteps.agent.application.checks import MAX_REPORTED
from scopesteps.agent.application.drafting import (
    DRAFT_PROMPTS,
    PROMPT_SCHEMAS,
    PromptName,
    draft_single_pass,
    prompt_version,
    sources_message,
)
from scopesteps.agent.application.naming import block_names, name_labels, name_labels_in
from scopesteps.agent.application.ports import ModelProvider, Passage
from scopesteps.agent.application.replying import (
    REPLY_PROMPT,
    REPLY_PROMPT_VERSION,
    REPLY_SCHEMA_VERSION,
    ReplyBlock,
    ReplyOutput,
    reply_request_text,
    reply_schema,
    resolve_claims,
)
from scopesteps.agent.application.schemas import DraftBacklogV4, SourceBlockInput
from scopesteps.agent.application.tools import (
    LOOKUP_SOURCE,
    REQUEST_CLARIFICATION,
    VALIDATE_BACKLOG,
    Clarification,
    answers_output,
    run_tool,
)
from scopesteps.agent.application.tracing import current_attributes, trace_scope
from scopesteps.agent.domain.budget import (
    BudgetExceededError,
    check_can_call,
    check_cost,
    estimate_tokens,
)
from scopesteps.agent.domain.conversation import Claim, Message
from scopesteps.agent.domain.ids import QuestionId, StepId
from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    ToolResult,
    ToolResults,
    Turn,
    Usage,
    UserMessage,
)
from scopesteps.agent.domain.pricing import estimate_cost_microusd
from scopesteps.agent.domain.run import (
    Question,
    QuestionStatus,
    Run,
    RunError,
    RunStage,
    RunStatus,
    RunStep,
    with_call,
)
from scopesteps.backlog.client import BacklogOutline, CandidateProposal
from scopesteps.projects.client import ExtractedPerson

DRAFT_PROMPT: PromptName = "draft-v7"
ExploreName = Literal["explore-v1", "explore-v2"]
_EXPLORE_V1 = """
Before drafting:
- Ask the reviewer with request_clarification when an answer would change the scope: a conflict
  between sources, a missing decision, or a vague requirement. Ask each question once, cite the
  blocks it is about, and ask nothing the sources already answer.
- Use lookup_source only to re-read blocks; every source is already in the first message.
- When nothing more needs asking, reply READY without calling a tool. The draft comes next.
"""
# explore-v2 follows the first agent evaluation (evals/README.md, "Agent runs"): v1 merged two
# decisions into one question, asked about deferred proposals and re-asked skipped questions.
_EXPLORE_V2 = """
Before drafting:
- Ask the reviewer with request_clarification when an answer would change the scope: a conflict
  between sources, a missing decision, or a vague requirement. Cite the blocks each question is
  about, and ask nothing the sources already answer.
- Ask one question per decision. When two decisions come up together, for example the
  cancellation deadline and what happens after a no-show, ask two questions.
- Do not ask about a proposal the sources defer or an exclusion they state; both stay as they are.
- Never ask again about a question the reviewer skipped. It stays an open decision.
- Use lookup_source only to re-read blocks; every source is already in the first message.
- When nothing more needs asking, reply READY without calling a tool. The draft comes next.
"""
EXPLORE_PROMPTS: dict[ExploreName, str] = {
    "explore-v1": DRAFT_PROMPTS[DRAFT_PROMPT] + _EXPLORE_V1,
    "explore-v2": DRAFT_PROMPTS[DRAFT_PROMPT] + _EXPLORE_V2,
}
AGENT_EXPLORE: ExploreName = "explore-v1"
"""The explore prompt agent runs use. A new version is adopted only after it is measured."""
EXPLORE_PROMPT = EXPLORE_PROMPTS[AGENT_EXPLORE]
EXPLORE_TASK = (
    "Read the sources and decide what the reviewer must answer before the backlog can be drafted."
)


def explore_prompt_version(name: ExploreName = AGENT_EXPLORE) -> str:
    return f"{name}+{hashlib.sha256(EXPLORE_PROMPTS[name].encode()).hexdigest()[:12]}"


def agent_prompt_version(explore: ExploreName = AGENT_EXPLORE) -> str:
    return f"{explore_prompt_version(explore)},{prompt_version(DRAFT_PROMPT)}"


EXPLORE_PROMPT_VERSION = explore_prompt_version()
AGENT_PROMPT_VERSION = agent_prompt_version()
AGENT_SCHEMA_VERSION = PROMPT_SCHEMAS[DRAFT_PROMPT]
DRAFT_CALLS = 2
"""A draft step may make its call plus one repair, so it reserves room for both."""
VALIDATE_REPLY = "validate_reply"
"""Resolves a reply's citations in code. Recorded as a tool step with counts only."""
VALIDATE_CHANGE = "validate_change"
"""Runs the change-set checks in code. Recorded as a tool step with counts and codes only."""


@dataclass(frozen=True)
class StepContext:
    provider: ModelProvider
    passages: Sequence[Passage]
    questions: Sequence[Question]
    project_spent_microusd: int
    project_limit_microusd: int | None
    now: datetime
    new_id: Callable[[], UUID]
    explore: ExploreName = AGENT_EXPLORE


@dataclass(frozen=True)
class StepOutcome:
    run: Run
    steps: tuple[RunStep, ...] = ()
    questions: tuple[Question, ...] = ()
    candidate: CandidateProposal | None = None
    """The backlog a finished draft proposes. The caller validates and saves it with the run."""
    people: tuple[ExtractedPerson, ...] = ()
    """The people a finished draft names. The caller hands them to the projects module."""
    claims: tuple[Claim, ...] = ()
    """A reply run's answer, with its citations resolved. The caller stores it as a message."""
    change: ChangeResult | None = None
    """What a change run's finished analysis proposes. The caller saves and records it."""


@dataclass(frozen=True)
class ChangeInput:
    """What a change run reads besides its pinned sources: the baseline under the labels the
    model sees. `StepContext.questions` holds this run's own questions."""

    labels: BaselineLabels


@dataclass(frozen=True)
class _ExplorePlan:
    system: str
    prompt_version: str
    next_stage: RunStage
    first_message: Callable[[Sequence[SourceBlockInput]], str]


@dataclass(frozen=True)
class ReplyInput:
    """What a reply reads besides the pinned sources. `StepContext.questions` holds the
    project's answered questions, which the reply may cite as A1, A2, ..."""

    message: Message
    earlier: Sequence[Message]
    backlog: BacklogOutline | None


def source_blocks(
    passages: Sequence[Passage], request_version_id: UUID | None = None
) -> list[SourceBlockInput]:
    """Number pinned paragraphs B1..Bn, in the order the run pinned their versions.

    A label names the source's kind and paragraph number ("brief paragraph 3"). When a run pins
    several versions of one kind, they are numbered in pinned order ("transcript 2 paragraph 3"),
    so no two blocks share a label and no uploader-chosen text such as a filename enters it.
    In a change run, `request_version_id` is its request: only that one is the "change request";
    requests the baseline already took in are each an "earlier change request".
    """

    def kind_of(p: Passage) -> str:
        kind = p.source_kind.replace("_", " ")
        if p.source_kind == CHANGE_REQUEST_KIND and p.source_version_id != request_version_id:
            return f"earlier {kind}"
        return kind

    versions_of_kind: dict[str, list[UUID]] = {}
    for p in passages:
        versions = versions_of_kind.setdefault(kind_of(p), [])
        if p.source_version_id not in versions:
            versions.append(p.source_version_id)

    def label(p: Passage) -> str:
        kind = kind_of(p)
        versions = versions_of_kind[kind]
        if len(versions) > 1:
            kind = f"{kind} {versions.index(p.source_version_id) + 1}"
        return f"{kind} paragraph {p.ordinal}"

    return [
        SourceBlockInput(f"B{index}", label(p), p.text, p.speakers)
        for index, p in enumerate(passages, start=1)
    ]


def answer_blocks(questions: Sequence[Question]) -> list[SourceBlockInput]:
    """Answers become A1..An; skipped questions stay explicit open decisions U1..Un."""
    blocks: list[SourceBlockInput] = []
    for question in questions:
        if question.answer_label is None:
            continue
        if question.status == QuestionStatus.ANSWERED and question.answer is not None:
            blocks.append(
                SourceBlockInput(question.answer_label, "reviewer answer", question.answer)
            )
        else:
            blocks.append(
                SourceBlockInput(
                    question.answer_label,
                    "open decision",
                    f"The reviewer has not answered this yet: {question.text}",
                )
            )
    return blocks


def answers_turn(run: Run, round_questions: Sequence[Question]) -> ToolResults:
    """The deferred tool result that resumes the conversation after a clarification round."""
    call_id = round_questions[0].call_id
    return ToolResults(
        (
            *run.pending_results,
            ToolResult(
                call_id, REQUEST_CLARIFICATION.name, answers_output(answer_blocks(round_questions))
            ),
        )
    )


def take_step(run: Run, context: StepContext, change: ChangeInput | None = None) -> StepOutcome:
    """One step of an initial run, or of a change run when `change` is given."""
    limits = run.inputs.limits
    may_explore = (
        run.stage == RunStage.EXPLORE
        and run.counters.model_turns + 1 + DRAFT_CALLS <= limits.max_turns
        and run.counters.tool_calls < limits.max_tool_calls
    )
    try:
        if change is not None:
            if may_explore:
                return _explore(run, context, _change_plan(change, context))
            return _change(replace(run, stage=RunStage.CHANGE), context, change)
        if may_explore:
            return _explore(run, context, _initial_plan(context))
        return _draft(replace(run, stage=RunStage.DRAFT), context)
    except BudgetExceededError as error:
        return StepOutcome(
            replace(
                run,
                status=RunStatus.FAILED,
                error=RunError(error.code, error.message, retryable=False),
            )
        )


def take_reply_step(run: Run, context: StepContext, reply: ReplyInput) -> StepOutcome:
    """One reply: a single call with no tools, so the model can only write text. Its citations
    are resolved in code and nothing else changes (ADR 0010)."""
    blocks = reply_blocks(context.passages, context.questions)
    text = reply_request_text(blocks, reply.backlog, reply.earlier, reply.message.text)
    try:
        _check_budget(run, context, estimate_tokens(REPLY_PROMPT + text), calls=1)
    except BudgetExceededError as error:
        return StepOutcome(
            replace(
                run,
                status=RunStatus.FAILED,
                error=RunError(error.code, error.message, retryable=False),
            )
        )
    request = ModelRequest(
        system_instruction=REPLY_PROMPT,
        history=(UserMessage(text),),
        max_output_tokens=run.inputs.limits.max_output_tokens_per_call,
        output_schema=reply_schema([block.id for block in blocks]),
    )
    recorder = RecordingProvider(context.provider, schema_version=REPLY_SCHEMA_VERSION)
    try:
        with trace_scope(
            run_id=str(run.id), stage=RunStage.REPLY.value, prompt_version=REPLY_PROMPT_VERSION
        ):
            result = recorder.generate(request)
    except ModelProviderError as error:
        run, steps = _apply_calls(run, recorder.calls, context, RunStage.REPLY)
        return StepOutcome(_after_provider_error(run, error), steps)
    run, steps = _apply_calls(run, recorder.calls, context, RunStage.REPLY)
    try:
        output = ReplyOutput.model_validate_json(result.text or "")
    except ValidationError:
        invalid = _tool_step(run, context, VALIDATE_REPLY, RunStage.REPLY, {"valid": False})
        return StepOutcome(_invalid_reply(run, "did not return a valid reply"), (*steps, invalid))
    claims = resolve_claims(output, {block.id: block for block in blocks})
    offered = sum(len(claim.citations) for claim in output.claims)
    kept = sum(len(claim.citations) for claim in claims)
    validation = _tool_step(
        run,
        context,
        VALIDATE_REPLY,
        RunStage.REPLY,
        {
            "valid": True,
            "claims": len(claims),
            "cited_claims": sum(1 for claim in claims if claim.basis == "cited"),
            "dropped_citations": max(offered - kept, 0),
        },
    )
    if not claims:
        return StepOutcome(_invalid_reply(run, "returned an empty reply"), (*steps, validation))
    return StepOutcome(
        replace(run, status=RunStatus.COMPLETED, error=None), (*steps, validation), claims=claims
    )


def _invalid_reply(run: Run, what: str) -> Run:
    return replace(
        run,
        status=RunStatus.FAILED,
        error=RunError(
            "INVALID_MODEL_OUTPUT", f"The model {what}. Send the message again.", retryable=False
        ),
    )


def reply_blocks(passages: Sequence[Passage], answers: Sequence[Question]) -> list[ReplyBlock]:
    """Pinned paragraphs as B1..Bn, labelled as in runs, then recorded answers as A1..An."""
    sources = [
        ReplyBlock(
            block.id,
            block.label,
            block.text,
            source_version_id=passage.source_version_id,
            block_id=passage.block_id,
        )
        for block, passage in zip(source_blocks(passages), passages, strict=True)
    ]
    answered = [q for q in answers if q.status == QuestionStatus.ANSWERED and q.answer]
    recorded = [
        ReplyBlock(
            f"A{index}",
            "reviewer answer",
            question.answer or "",
            question_id=question.id,
            question=question.text,
        )
        for index, question in enumerate(answered, start=1)
    ]
    return [*sources, *recorded]


def _initial_plan(context: StepContext) -> _ExplorePlan:
    return _ExplorePlan(
        system=EXPLORE_PROMPTS[context.explore],
        prompt_version=explore_prompt_version(context.explore),
        next_stage=RunStage.DRAFT,
        first_message=lambda blocks: sources_message(blocks, EXPLORE_TASK, DRAFT_PROMPT),
    )


def _change_plan(change: ChangeInput, context: StepContext) -> _ExplorePlan:
    return _ExplorePlan(
        system=CHANGE_EXPLORE_PROMPT,
        prompt_version=CHANGE_EXPLORE_VERSION,
        next_stage=RunStage.CHANGE,
        first_message=lambda blocks: change_message(
            change.labels, blocks, context.passages, CHANGE_EXPLORE_TASK
        ),
    )


def request_version(run: Run) -> UUID | None:
    """The source version holding a change run's own request; None for other runs."""
    return run.inputs.change.request_version_id if run.inputs.change else None


def _explore(run: Run, context: StepContext, plan: _ExplorePlan) -> StepOutcome:
    blocks = [
        *source_blocks(context.passages, request_version(run)),
        *answer_blocks(context.questions),
    ]
    history: tuple[Turn, ...] = run.history or (UserMessage(plan.first_message(blocks)),)
    system = plan.system
    estimated = estimate_tokens(system + _history_text(history))
    _check_budget(run, context, estimated, calls=1)
    may_ask = run.clarification_rounds < run.inputs.max_clarification_rounds
    request = ModelRequest(
        system_instruction=system,
        history=history,
        max_output_tokens=run.inputs.limits.max_output_tokens_per_call,
        tools=(LOOKUP_SOURCE, REQUEST_CLARIFICATION) if may_ask else (LOOKUP_SOURCE,),
        tool_choice="auto",
    )
    recorder = RecordingProvider(context.provider)
    try:
        with trace_scope(
            run_id=str(run.id),
            stage=RunStage.EXPLORE.value,
            prompt_version=plan.prompt_version,
        ):
            result = recorder.generate(request)
    except ModelProviderError as error:
        run, steps = _apply_calls(run, recorder.calls, context, RunStage.EXPLORE)
        return StepOutcome(_after_provider_error(run, error), steps)
    run, steps = _apply_calls(run, recorder.calls, context, RunStage.EXPLORE)

    if not result.tool_calls:
        return StepOutcome(
            replace(run, history=(*history, result.turn), stage=plan.next_stage, error=None),
            steps,
        )

    results: list[ToolResult] = []
    clarification: Clarification | None = None
    tool_steps: list[RunStep] = []
    for call in result.tool_calls:
        outcome = run_tool(call, blocks, may_ask=may_ask and clarification is None)
        if isinstance(outcome, Clarification):
            clarification = outcome
        else:
            results.append(outcome)
        tool_steps.append(
            _tool_step(
                run,
                context,
                call.name,
                RunStage.EXPLORE,
                {"is_error": isinstance(outcome, ToolResult) and outcome.is_error},
            )
        )
    steps = (*steps, *tool_steps)

    if clarification is None:
        return StepOutcome(
            replace(
                run,
                history=(*history, result.turn, ToolResults(tuple(results))),
                error=None,
            ),
            steps,
        )
    round_number = run.clarification_rounds + 1
    names = block_names(blocks)
    questions = tuple(
        Question(
            id=QuestionId(context.new_id()),
            run_id=run.id,
            round=round_number,
            call_id=clarification.call_id,
            subject=name_labels(asked.subject, names),
            text=name_labels(asked.question, names),
            why_it_matters=name_labels(asked.why_it_matters, names),
            block_labels=tuple(asked.block_ids),
        )
        for asked in clarification.args.questions
    )
    return StepOutcome(
        replace(
            run,
            history=(*history, result.turn),
            pending_results=tuple(results),
            status=RunStatus.WAITING_FOR_INPUT,
            clarification_rounds=round_number,
            error=None,
        ),
        steps,
        questions,
    )


def _draft(run: Run, context: StepContext) -> StepOutcome:
    answers = answer_blocks(context.questions)
    blocks = [*source_blocks(context.passages), *answers]
    estimated = estimate_tokens(
        DRAFT_PROMPTS[DRAFT_PROMPT] + sources_message(blocks, "", DRAFT_PROMPT)
    )
    _check_budget(run, context, estimated, calls=DRAFT_CALLS)
    answered = {b.id for b in answers if b.label == "reviewer answer"}
    recorder = RecordingProvider(context.provider)
    try:
        with trace_scope(run_id=str(run.id), stage=RunStage.DRAFT.value):
            outcome = draft_single_pass(
                recorder,
                blocks,
                max_output_tokens=run.inputs.limits.max_output_tokens_per_call,
                with_answers=bool(answered),
                open_decision_blocks={b.id for b in answers if b.id not in answered},
                answer_blocks=answered,
                prompt=DRAFT_PROMPT,
            )
    except ModelProviderError as error:
        run, steps = _apply_calls(run, recorder.calls, context, RunStage.DRAFT)
        return StepOutcome(_after_provider_error(run, error), steps)
    run, steps = _apply_calls(run, recorder.calls, context, RunStage.DRAFT)
    validation = _tool_step(
        run,
        context,
        VALIDATE_BACKLOG,
        RunStage.DRAFT,
        {
            "problems": len(outcome.check_problems),
            "repair": outcome.repair,
            "repaired": outcome.repaired,
            "repair_triggers": list(outcome.repair_triggers),
        },
    )
    steps = (*steps, validation)
    if outcome.draft is None:
        return StepOutcome(
            replace(
                run,
                status=RunStatus.FAILED,
                error=RunError(
                    "INVALID_MODEL_OUTPUT",
                    "The model did not return a valid draft after its repair attempt",
                    retryable=False,
                ),
            ),
            steps,
        )
    if not isinstance(outcome.draft, DraftBacklogV4):
        raise TypeError(f"{DRAFT_PROMPT} must produce a draft-backlog.v4 draft")
    # Checked against the labels the model saw; stored with the names people see.
    draft = DraftBacklogV4.model_validate(
        name_labels_in(outcome.draft.model_dump(), block_names(blocks))
    )
    by_label = {
        block.id: passage
        for block, passage in zip(source_blocks(context.passages), context.passages, strict=True)
    }
    return StepOutcome(
        replace(
            run,
            status=RunStatus.READY_FOR_REVIEW,
            draft=draft.model_dump(),
            problems=outcome.check_problems,
            error=None,
        ),
        steps,
        candidate=to_proposal(run, draft, by_label, context.questions),
        people=to_people(draft, by_label),
    )


def _change(run: Run, context: StepContext, change: ChangeInput) -> StepOutcome:
    """The change set with its single repair: one call, and one more only if the output does not
    parse or fails a check. A change set that still fails is refused, never saved (ADR 0011)."""
    sources = source_blocks(context.passages, request_version(run))
    answers = answer_blocks(context.questions)
    blocks = [*sources, *answers]
    text = change_message(change.labels, blocks, context.passages, CHANGE_TASK)
    _check_budget(run, context, estimate_tokens(CHANGE_PROMPT + text), calls=DRAFT_CALLS)
    first = UserMessage(text)
    schema = change_schema(change.labels, [block.id for block in blocks])
    request = ModelRequest(
        system_instruction=CHANGE_PROMPT,
        history=(first,),
        max_output_tokens=run.inputs.limits.max_output_tokens_per_call,
        output_schema=schema,
    )
    request_blocks = {
        block.id
        for block, passage in zip(sources, context.passages, strict=True)
        if passage.source_version_id == request_version(run)
    }
    texts = {block.id: block.text for block in blocks}
    block_labels: dict[UUID, str] = {
        passage.block_id: block.id for block, passage in zip(sources, context.passages, strict=True)
    }
    answered = {block.id for block in answers if block.label == "reviewer answer"}
    recorder = RecordingProvider(context.provider, schema_version=CHANGE_SCHEMA_VERSION)
    output: ChangeSetOutput | None = None
    problems: list[str] = []
    triggers: list[str] = []
    try:
        with trace_scope(
            run_id=str(run.id), stage=RunStage.CHANGE.value, prompt_version=CHANGE_STEP_VERSION
        ):
            for attempt in (1, 2):
                repair = "none" if attempt == 1 else "full"
                with trace_scope(attempt=attempt, repair=repair):
                    result = recorder.generate(request)
                try:
                    output = ChangeSetOutput.model_validate_json(result.text or "")
                except ValidationError as error:
                    output = None
                    problems = [_summarize(error)]
                    codes = ["invalid_output"]
                else:
                    found = find_change_problems(
                        output,
                        change.labels,
                        texts,
                        request_blocks=request_blocks,
                        answer_blocks=answered,
                        block_labels=block_labels,
                    )
                    problems = [problem.message for problem in found]
                    codes = sorted({problem.code for problem in found})
                if not problems or attempt == 2:
                    break
                triggers = codes
                listed = "\n".join(f"- {problem}" for problem in problems[:MAX_REPORTED])
                request = replace(
                    request,
                    history=(
                        first,
                        result.turn,
                        UserMessage(REPAIR_INSTRUCTION.format(problems=listed)),
                    ),
                )
    except ModelProviderError as error:
        run, steps = _apply_calls(run, recorder.calls, context, RunStage.CHANGE)
        return StepOutcome(_after_provider_error(run, error), steps)
    run, steps = _apply_calls(run, recorder.calls, context, RunStage.CHANGE)
    validation = _tool_step(
        run,
        context,
        VALIDATE_CHANGE,
        RunStage.CHANGE,
        {
            "valid": output is not None,
            "problems": len(problems),
            "repaired": bool(triggers) and not problems,
            "repair_triggers": triggers,
            "outcome": "" if output is None else output.outcome,
            "operations": 0 if output is None else len(output.operations),
            "scope_decisions": 0 if output is None else len(output.scope_decisions),
        },
    )
    steps = (*steps, validation)
    if output is None or problems:
        return StepOutcome(
            replace(
                run,
                status=RunStatus.FAILED,
                problems=tuple(problems[:MAX_REPORTED]),
                error=RunError(
                    "INVALID_MODEL_OUTPUT" if output is None else "CHANGE_REJECTED",
                    "The analysis did not produce a valid change set, so nothing was proposed. "
                    "Send the change request again.",
                    retryable=False,
                ),
            ),
            steps,
        )
    # Checked against the labels the model saw; stored with the names people see.
    added = {
        op.item: f'"{op.title}"' for op in output.operations if op.op == "add_item" and op.title
    }
    output = ChangeSetOutput.model_validate(
        name_labels_in(
            output.model_dump(), {**block_names(blocks), **change.labels.names(), **added}
        )
    )
    by_label = {block.id: passage for block, passage in zip(sources, context.passages, strict=True)}
    result_change = to_change_proposal(run, output, change.labels, by_label, context.questions)
    finished = RunStatus.COMPLETED if result_change.proposal is None else RunStatus.READY_FOR_REVIEW
    return StepOutcome(
        replace(run, status=finished, draft=output.model_dump(), problems=(), error=None),
        steps,
        change=result_change,
    )


def _summarize(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'root'}: {item['msg']}"
        for item in error.errors()[:5]
    )


def _check_budget(run: Run, context: StepContext, estimated_input: int, *, calls: int) -> None:
    limits = run.inputs.limits
    check_can_call(run.counters, limits, estimated_input, calls=calls)
    worst = estimate_cost_microusd(
        run.inputs.model_id,
        Usage(
            input_tokens=calls * estimated_input,
            output_tokens=calls * limits.max_output_tokens_per_call,
        ),
    )
    check_cost(
        worst_case_microusd=worst,
        run_spent_microusd=run.totals.cost_microusd,
        project_spent_microusd=context.project_spent_microusd,
        run_limit_microusd=limits.max_cost_microusd,
        project_limit_microusd=context.project_limit_microusd,
    )


def _after_provider_error(run: Run, error: ModelProviderError) -> Run:
    """Transient failures leave the run advanceable; the next advance tries again within limits."""
    return replace(
        run,
        status=RunStatus.RUNNING if error.retryable else RunStatus.FAILED,
        error=RunError(f"MODEL_{error.kind.upper()}", error.message, error.retryable),
    )


@dataclass(frozen=True)
class RecordedCall:
    result: ModelResult | None
    error: ModelProviderError | None
    latency_ms: int
    attempt: int
    repair: str
    prompt_version: str
    schema_version: str


@dataclass
class RecordingProvider:
    """Captures every call, success or failure, so each is persisted as a run step."""

    inner: ModelProvider
    calls: list[RecordedCall] = field(default_factory=list[RecordedCall])
    schema_version: str = AGENT_SCHEMA_VERSION
    """Recorded on calls that ask for structured output."""

    def generate(self, request: ModelRequest) -> ModelResult:
        attributes = current_attributes()
        started = time.perf_counter()
        error: ModelProviderError | None = None
        result: ModelResult | None = None
        try:
            result = self.inner.generate(request)
            return result
        except ModelProviderError as failure:
            error = failure
            raise
        finally:
            self.calls.append(
                RecordedCall(
                    result=result,
                    error=error,
                    latency_ms=result.latency_ms
                    if result is not None
                    else round((time.perf_counter() - started) * 1000),
                    attempt=int(attributes.get("scopesteps.attempt") or 1),
                    repair=str(attributes.get("scopesteps.repair") or "none"),
                    prompt_version=str(attributes.get("scopesteps.prompt_version") or ""),
                    schema_version=self.schema_version if request.output_schema else "",
                )
            )


def _apply_calls(
    run: Run, calls: Sequence[RecordedCall], context: StepContext, stage: RunStage
) -> tuple[Run, tuple[RunStep, ...]]:
    steps: list[RunStep] = []
    for call in calls:
        if call.result is None:
            run = replace(run, counters=run.counters.after_failed_call())
            cost = None
        else:
            cost = estimate_cost_microusd(call.result.model_id, call.result.usage)
            run = with_call(run, call.result, cost)
        usage = call.result.usage if call.result else Usage()
        steps.append(
            RunStep(
                id=StepId(context.new_id()),
                run_id=run.id,
                kind="model_call",
                name="generate",
                stage=stage,
                created_at=context.now,
                provider=run.inputs.provider,
                model_id=call.result.model_id if call.result else run.inputs.model_id,
                prompt_version=call.prompt_version,
                schema_version=call.schema_version,
                attempt=call.attempt,
                repair=call.repair,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                thinking_tokens=usage.thinking_tokens,
                latency_ms=call.latency_ms,
                finish_reason=call.result.finish_reason if call.result else "",
                tool_calls=len(call.result.tool_calls) if call.result else 0,
                error_kind=call.error.kind if call.error else None,
                cost_microusd=cost,
            )
        )
    return run, tuple(steps)


def _tool_step(
    run: Run, context: StepContext, name: str, stage: RunStage, detail: dict[str, object]
) -> RunStep:
    return RunStep(
        id=StepId(context.new_id()),
        run_id=run.id,
        kind="tool",
        name=name,
        stage=stage,
        created_at=context.now,
        detail=detail,
    )


def _history_text(history: Sequence[Turn]) -> str:
    parts: list[str] = []
    for turn in history:
        match turn:
            case UserMessage(text=text):
                parts.append(text)
            case ModelTurn(steps=steps):
                parts.append(json.dumps(steps, default=str))
            case ToolResults(results=results):
                parts.extend(json.dumps(r.output, default=str) for r in results)
    return "\n".join(parts)
