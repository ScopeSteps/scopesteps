"""Drafting in steps (draft-v11, ADR 0028).

An outline call reads every source and lists every statement, the epics the confirmed ones group
into, the clarification questions and the people. Then one call per epic writes that epic's
stories from the paragraphs its statements cite and those around them. Each step is checked in
code and repaired once. Code numbers the stories and puts the backlog together, so no single call
has to hold a whole large backlog, and the draft is checked again as a whole.

Finished steps are kept in `StepwiseProgress`, so a step that fails at the provider is tried again
on its own: the evaluation runner resumes from it, and an agent run stores it between advances.
"""

import html
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from scopesteps.agent.application.checks import (
    MAX_REPORTED,
    Problem,
    ProblemCode,
    find_problems,
    requirement_blocks,
)
from scopesteps.agent.application.drafting import (
    ANSWERS_INSTRUCTION,
    CONCISE_RETRY_INSTRUCTION,
    DRAFT_PROMPTS,
    OPEN_DECISIONS_INSTRUCTION,
    PROMPT_CHECKS,
    QUOTED_EPIC_PROMPTS,
    REPAIR_INSTRUCTION,
    STEP_PROMPTS,
    DraftOutcome,
    PromptName,
    RepairKind,
    invalid_output_trigger,
    prompt_version,
    sources_message,
    summarize_validation,
)
from scopesteps.agent.application.ports import ModelProvider
from scopesteps.agent.application.schemas import (
    STATEMENT_IDS_V6,
    DraftBacklogV6,
    DraftOutline,
    EpicStories,
    OutlineEpic,
    OutlinePatch,
    SourceBlockInput,
    apply_outline_patch,
    constrain_ids,
    provider_schema,
)
from scopesteps.agent.application.speakers import participants_of
from scopesteps.agent.application.tracing import trace_scope
from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    Turn,
    Usage,
    UserMessage,
)

STEPWISE_PROMPT: PromptName = "draft-v11"
OUTLINE_SCHEMA_VERSION = "draft-backlog.v6+outline"
EPIC_SCHEMA_VERSION = "draft-backlog.v6+epic"
WINDOW = 2
"""Paragraphs shown on each side of a cited one in an epic step, so a story can use what was
said just before and after without the call carrying every source."""
STEP_CALLS = 2
"""Each step makes its call plus at most one repair."""

_STORY_CHECKS: frozenset[ProblemCode] = frozenset(
    {
        "uncovered_confirmed_statement",
        "story_format",
        "story_without_criteria",
        "unused_reviewer_answer",
    }
)
_PLAN_CHECKS: frozenset[ProblemCode] = frozenset({"unplanned_statement", "empty_epic"})
OUTLINE_CHECKS: frozenset[ProblemCode] = (
    frozenset(PROMPT_CHECKS[STEPWISE_PROMPT]) - _STORY_CHECKS
) | _PLAN_CHECKS
"""What the outline alone can get wrong. Stories, and the answers their criteria cite, come later."""
EPIC_CHECKS: frozenset[ProblemCode] = frozenset(
    {
        "unknown_block",
        "quote_not_verbatim",
        "story_format",
        "story_without_criteria",
        "uncovered_confirmed_statement",
        "unused_reviewer_answer",
    }
)

OUTLINE_TASK = "Write the outline as JSON."
EPIC_TASK = "Write the stories of epic {ref} as JSON."
OUTLINE_PATCH_INSTRUCTION = (
    "The outline has these problems:\n{problems}\nFix only these. Return JSON with just the "
    "statements, epics, questions and people you add or change. Reuse an id or ref to replace "
    "that statement, epic or person in full, or use a new one to add it. Set replaces to a "
    "question's number to replace that question, or null to add one. Everything you leave out "
    "is kept as it is."
)


@dataclass
class StepResult[T: BaseModel]:
    """One step's output after its repair, or None when it never validated."""

    output: T | None
    error: str | None = None
    repair: RepairKind = "none"
    triggers: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()
    repair_error: str | None = None


@dataclass
class StepwiseProgress:
    """The finished steps of one draft, kept so a failed step is retried without redoing them."""

    outline: StepResult[DraftOutline] | None = None
    epics: dict[str, StepResult[EpicStories]] = field(
        default_factory=dict[str, StepResult[EpicStories]]
    )
    results: list[ModelResult] = field(default_factory=list[ModelResult])
    """Every completed call, across retries, so usage is never lost."""

    def next_epic(self) -> OutlineEpic | None:
        """The first epic still to write, or None when the outline is missing or all are done."""
        if self.outline is None or self.outline.output is None:
            return None
        return next(
            (e for e in written_epics(self.outline.output) if e.ref not in self.epics), None
        )


def written_epics(outline: DraftOutline) -> list[OutlineEpic]:
    """The epics that get stories: those planned to implement at least one confirmed statement.
    An epic with none is reported (`empty_epic`) and left out of the draft."""
    confirmed = {s.id for s in outline.statements if s.kind == "confirmed"}
    return [epic for epic in outline.epics if set(epic.covers) & confirmed]


@dataclass(frozen=True)
class DraftInputs:
    """What every step of one draft reads."""

    blocks: Sequence[SourceBlockInput]
    max_output_tokens: int
    with_answers: bool = False
    open_decision_blocks: Collection[str] = ()
    answer_blocks: Collection[str] = ()
    prompt: PromptName = STEPWISE_PROMPT

    @property
    def document_blocks(self) -> list[str]:
        """Paragraphs a statement must cite: documents, not speech. Small talk in a long meeting
        needs no statement, so only paragraphs without speakers are accounted for."""
        spoken = {block.id for block in self.blocks if block.speakers}
        return [
            block_id
            for block_id in requirement_blocks(
                self.blocks, exclude={*self.open_decision_blocks, *self.answer_blocks}
            )
            if block_id not in spoken
        ]


def outline_step(
    provider: ModelProvider, inputs: DraftInputs
) -> tuple[StepResult[DraftOutline], list[ModelResult]]:
    """The outline call with its single repair. Provider errors on the first call propagate."""
    task = OUTLINE_TASK
    if inputs.with_answers:
        task = f"{ANSWERS_INSTRUCTION} {task}"
    if inputs.open_decision_blocks:
        task += " " + OPEN_DECISIONS_INSTRUCTION.format(
            blocks=", ".join(sorted(inputs.open_decision_blocks))
        )
    first = UserMessage(sources_message(inputs.blocks, task, inputs.prompt))
    retry = UserMessage(
        sources_message(inputs.blocks, f"{task} {CONCISE_RETRY_INSTRUCTION}", inputs.prompt)
    )
    block_ids = [block.id for block in inputs.blocks]
    speaker_ids = list(participants_of(block.speakers for block in inputs.blocks).notes)

    def schema(model: type[BaseModel]) -> dict[str, Any]:
        return constrain_ids(provider_schema(model), block_ids, speaker_ids, STATEMENT_IDS_V6)

    return _run_step(
        provider,
        system=DRAFT_PROMPTS[inputs.prompt],
        first=first,
        retry=retry,
        model=DraftOutline,
        schema=schema(DraftOutline),
        patch=(OutlinePatch, schema(OutlinePatch), apply_outline_patch, OUTLINE_PATCH_INSTRUCTION),
        check=lambda outline: outline_problems(outline, inputs),
        max_output_tokens=inputs.max_output_tokens,
        version=prompt_version(inputs.prompt),
    )


def epic_step(
    provider: ModelProvider, inputs: DraftInputs, outline: DraftOutline, epic: OutlineEpic
) -> tuple[StepResult[EpicStories], list[ModelResult]]:
    """One epic's stories with their single repair. Provider errors on the first call propagate."""
    window = epic_blocks(inputs.blocks, outline, epic)
    quoted = inputs.prompt in QUOTED_EPIC_PROMPTS
    task = EPIC_TASK.format(ref=epic.ref)
    text = epic_message(outline, epic, window, task, quotes=quoted)
    concise = epic_message(
        outline, epic, window, f"{task} {CONCISE_RETRY_INSTRUCTION}", quotes=quoted
    )
    schema = constrain_ids(
        provider_schema(EpicStories),
        [block.id for block in window],
        cover_ids=[ref for ref in epic.covers if _kind(outline, ref) == "confirmed"],
    )
    return _run_step(
        provider,
        system=STEP_PROMPTS[inputs.prompt],
        first=UserMessage(text),
        retry=UserMessage(concise),
        model=EpicStories,
        schema=schema,
        patch=None,
        check=lambda stories: epic_problems(stories, outline, epic, inputs),
        max_output_tokens=inputs.max_output_tokens,
        version=prompt_version(inputs.prompt),
    )


def draft_in_steps(
    provider: ModelProvider, inputs: DraftInputs, progress: StepwiseProgress | None = None
) -> DraftOutcome:
    """Every step of a draft, resuming from `progress` when given. Provider errors propagate with
    the finished steps kept in `progress`, so calling again tries only the failed step."""
    progress = progress if progress is not None else StepwiseProgress()
    version = prompt_version(inputs.prompt)
    if progress.outline is None:
        with trace_scope(draft_step="outline"):
            progress.outline = _counted(progress, outline_step(provider, inputs))
    outline = progress.outline.output
    if outline is None:
        return _outcome(progress, None, f"outline: {progress.outline.error}", version)
    while (epic := progress.next_epic()) is not None:
        with trace_scope(draft_step=f"epic {epic.ref}"):
            result = _counted(progress, epic_step(provider, inputs, outline, epic))
        progress.epics[epic.ref] = result
        if result.output is None:
            return _outcome(
                progress, None, f"epic {epic.ref} '{epic.title[:60]}': {result.error}", version
            )
    return finish(progress, inputs)


def finish(progress: StepwiseProgress, inputs: DraftInputs) -> DraftOutcome:
    """Put the finished steps together and check the whole draft."""
    version = prompt_version(inputs.prompt)
    if progress.outline is None or progress.outline.output is None:
        return _outcome(progress, None, "outline: not written", version)
    outline = progress.outline.output
    written = [progress.epics.get(epic.ref) for epic in written_epics(outline)]
    stories = [result.output for result in written if result is not None and result.output]
    if len(stories) < len(written):
        return _outcome(progress, None, "an epic has no stories yet", version)
    try:
        draft = assemble(outline, stories)
    except ValidationError as error:
        return _outcome(progress, None, f"assembly: {summarize_validation(error)}", version)
    problems = find_problems(
        draft,
        inputs.blocks,
        open_decision_blocks=inputs.open_decision_blocks,
        answer_blocks=inputs.answer_blocks,
        account_blocks=inputs.document_blocks,
        enabled=PROMPT_CHECKS[inputs.prompt],
    )
    return _outcome(progress, draft, None, version, problems)


def assemble(outline: DraftOutline, epics: Sequence[EpicStories]) -> DraftBacklogV6:
    """The draft the steps describe: each epic followed by its stories, numbered S1, S2, ...
    across the backlog in epic order, and each question marked as affecting the stories that
    wait for it. A question number no question has is ignored."""
    items: list[dict[str, Any]] = []
    affects: dict[int, list[str]] = {}
    number = 0
    for epic, stories in zip(written_epics(outline), epics, strict=True):
        items.append(
            {
                "ref": epic.ref,
                "kind": "epic",
                "parent_ref": None,
                "title": epic.title,
                "description": epic.description,
                "criteria": [criterion.model_dump() for criterion in epic.criteria],
                "assumptions": [],
                "open_questions": [],
                "covers": [],
            }
        )
        for story in stories.stories:
            number += 1
            ref = f"S{number}"
            for waited in story.waits_for:
                affects.setdefault(waited, []).append(ref)
            items.append(
                {
                    "ref": ref,
                    "kind": "story",
                    "parent_ref": epic.ref,
                    "title": story.title,
                    "description": story.description,
                    "criteria": [criterion.model_dump() for criterion in story.criteria],
                    "assumptions": story.assumptions,
                    "open_questions": story.open_questions,
                    "covers": story.covers,
                }
            )
    questions = [
        question.model_dump() | {"affects": affects.get(index, [])}
        for index, question in enumerate(outline.questions, start=1)
    ]
    return DraftBacklogV6.model_validate(
        {
            "statements": [statement.model_dump() for statement in outline.statements],
            "items": items,
            "questions": questions,
            "people": [person.model_dump() for person in outline.people],
        }
    )


def outline_problems(outline: DraftOutline, inputs: DraftInputs) -> list[Problem]:
    """Problems in the outline: the draft checks that need no stories, on the outline as a
    draft of epics only, plus every confirmed statement planned into an epic."""
    as_draft = DraftBacklogV6.model_validate(
        {
            "statements": [statement.model_dump() for statement in outline.statements],
            "items": [
                {
                    "ref": epic.ref,
                    "kind": "epic",
                    "parent_ref": None,
                    "title": epic.title,
                    "description": epic.description,
                    "criteria": [criterion.model_dump() for criterion in epic.criteria],
                    "assumptions": [],
                    "open_questions": [],
                    "covers": epic.covers,
                }
                for epic in outline.epics
            ],
            "questions": [q.model_dump() | {"affects": []} for q in outline.questions],
            "people": [person.model_dump() for person in outline.people],
        }
    )
    problems = find_problems(
        as_draft,
        inputs.blocks,
        open_decision_blocks=inputs.open_decision_blocks,
        account_blocks=inputs.document_blocks,
        enabled=OUTLINE_CHECKS,
    )
    planned = {ref for epic in outline.epics for ref in epic.covers}
    confirmed = {s.id for s in outline.statements if s.kind == "confirmed"}
    problems += [
        Problem(
            "empty_epic",
            f"epic {epic.ref} covers no confirmed statement; list the confirmed statements its "
            "stories implement, or remove it",
        )
        for epic in outline.epics
        if not set(epic.covers) & confirmed
    ]
    problems += [
        Problem(
            "unplanned_statement",
            f"confirmed statement {statement.id} '{statement.summary[:60]}' is in no epic; add it "
            "to the covers of the epic it belongs to",
        )
        for statement in outline.statements
        if statement.kind == "confirmed" and statement.id not in planned
    ]
    return [problem for problem in problems if problem.code in OUTLINE_CHECKS]


def epic_problems(
    stories: EpicStories, outline: DraftOutline, epic: OutlineEpic, inputs: DraftInputs
) -> list[Problem]:
    """Problems in one epic's stories: citations, story format and criteria, every confirmed
    statement of the epic covered, and every reviewer answer those statements cite used."""
    covered = {ref for ref in epic.covers if _kind(outline, ref) == "confirmed"}
    statements = [s for s in outline.statements if s.id in covered]
    unknown = sorted({ref for story in stories.stories for ref in story.covers} - covered)
    if unknown:
        return [
            Problem(
                "uncovered_confirmed_statement",
                f"stories cover {', '.join(unknown)}, which are not statements of epic {epic.ref}; "
                f"cover only {', '.join(sorted(covered))}",
            )
        ]
    answers = {
        cite.block_id
        for statement in statements
        for cite in statement.citations
        if cite.block_id in set(inputs.answer_blocks)
    }
    as_draft = DraftBacklogV6.model_validate(
        {
            "statements": [statement.model_dump() for statement in statements],
            "items": [
                {
                    "ref": epic.ref,
                    "kind": "epic",
                    "parent_ref": None,
                    "title": epic.title,
                    "description": epic.description,
                    "criteria": [],
                    "assumptions": [],
                    "open_questions": [],
                    "covers": [],
                },
                *(
                    story.model_dump(exclude={"waits_for"})
                    | {"kind": "story", "parent_ref": epic.ref}
                    for story in stories.stories
                ),
            ],
            "questions": [],
            "people": [],
        }
    )
    return find_problems(as_draft, inputs.blocks, answer_blocks=answers, enabled=EPIC_CHECKS)


def epic_blocks(
    blocks: Sequence[SourceBlockInput], outline: DraftOutline, epic: OutlineEpic
) -> list[SourceBlockInput]:
    """The paragraphs an epic step sees, in source order: those its statements and criteria cite,
    `WINDOW` on each side of them, and every reviewer answer and open decision."""
    covered = set(epic.covers)
    cited = {
        cite.block_id
        for statement in outline.statements
        if statement.id in covered
        for cite in statement.citations
    } | {cite.block_id for criterion in epic.criteria for cite in criterion.citations}
    index = {block.id: position for position, block in enumerate(blocks)}
    shown: set[int] = set()
    for block_id in cited:
        if (position := index.get(block_id)) is not None:
            shown.update(range(max(0, position - WINDOW), position + WINDOW + 1))
    return [
        block
        for position, block in enumerate(blocks)
        if position in shown or block.label in {"reviewer answer", "open decision"}
    ]


def epic_message(
    outline: DraftOutline,
    epic: OutlineEpic,
    window: Sequence[SourceBlockInput],
    task: str,
    *,
    quotes: bool = False,
) -> str:
    """An epic step's request: the epic and its statements, the statements its paragraphs hold
    that are not in scope, the open questions, then the paragraphs. Outline text is model output
    drawn from the sources, so it is escaped and fenced like them. With `quotes` (draft-v12), each
    statement also shows its quotes, which the outline's checks found word for word in their
    blocks."""
    shown = {block.id for block in window}
    covered = set(epic.covers)

    def cites(ids: Sequence[str]) -> str:
        return html.escape(", ".join(ids))

    lines = [
        f'<epic ref="{epic.ref}" title="{html.escape(epic.title)}">'
        f"{html.escape(epic.description, quote=False)}</epic>",
        "<statements>",
    ]
    for statement in outline.statements:
        ids = [cite.block_id for cite in statement.citations]
        in_epic = statement.id in covered
        if not in_epic and (statement.kind == "context" or not set(ids) & shown):
            continue
        scope = "in this epic" if in_epic else "not in this epic"
        opening = (
            f'<statement id="{statement.id}" kind="{statement.kind}" scope="{scope}" '
            f'cites="{cites(ids)}">'
        )
        summary = html.escape(statement.summary, quote=False)
        if not quotes:
            lines.append(f"{opening}{summary}</statement>")
            continue
        exact = "".join(
            f'<quote block="{html.escape(cite.block_id)}">'
            f"{html.escape(cite.quote, quote=False)}</quote>"
            for cite in statement.citations
            if cite.block_id in shown
        )
        lines.append(f"{opening}<summary>{summary}</summary>{exact}</statement>")
    lines += ["</statements>", "<questions>"]
    for number, question in enumerate(outline.questions, start=1):
        ids = [cite.block_id for cite in question.citations]
        lines.append(
            f'<question number="{number}" cites="{cites(ids)}">'
            f"{html.escape(question.question, quote=False)}</question>"
        )
    lines.append("</questions>")
    tags = [
        f'<source id="{block.id}" label="{html.escape(block.label)}">'
        f"{html.escape(block.text, quote=False)}</source>"
        for block in window
    ]
    return "\n".join(lines) + "\n\n<sources>\n" + "\n".join(tags) + f"\n</sources>\n\nTask: {task}"


def _kind(outline: DraftOutline, statement_id: str) -> str | None:
    return next((s.kind for s in outline.statements if s.id == statement_id), None)


def _counted[T](progress: StepwiseProgress, step: tuple[T, list[ModelResult]]) -> T:
    result, made = step
    progress.results.extend(made)
    return result


def _run_step[T: BaseModel](
    provider: ModelProvider,
    *,
    system: str,
    first: UserMessage,
    retry: UserMessage,
    model: type[T],
    schema: dict[str, Any],
    patch: tuple[type[BaseModel], dict[str, Any], Callable[[T, Any], T], str] | None,
    check: Callable[[T], list[Problem]],
    max_output_tokens: int,
    version: str,
) -> tuple[StepResult[T], list[ModelResult]]:
    """One call and at most one repair. An answer cut off or empty is asked for again, more
    concisely; one that does not parse is sent back with its errors; one that fails a check is
    patched when the step has a patch schema and sent back whole otherwise. A repair that fails
    at the provider leaves the answer from before it, with its problems."""

    def request(history: tuple[Turn, ...], output_schema: dict[str, Any]) -> ModelRequest:
        return ModelRequest(
            system_instruction=system,
            history=history,
            max_output_tokens=max_output_tokens,
            output_schema=output_schema,
        )

    made: list[ModelResult] = []
    with trace_scope(prompt_version=version, attempt=1, repair="none"):
        result = provider.generate(request((first,), schema))
    made.append(result)
    error = ""
    try:
        best: T | None = model.model_validate_json(result.text or "")
    except ValidationError as failure:
        best = None
        error = summarize_validation(failure)
    problems: list[Problem] = []
    if best is None:
        repair: RepairKind = "full"
        triggers = (invalid_output_trigger(result),)
        if triggers[0] != "invalid_output":
            next_request = request((retry,), schema)
        else:
            next_request = request(
                (first, result.turn, UserMessage(REPAIR_INSTRUCTION.format(errors=error))), schema
            )
    else:
        problems = check(best)
        if not problems:
            return StepResult(best), made
        triggers = tuple(sorted({problem.code for problem in problems}))
        listed = "\n".join(f"- {problem.message}" for problem in problems[:MAX_REPORTED])
        if patch is not None:
            repair = "targeted"
            instruction = UserMessage(patch[3].format(problems=listed))
            next_request = request((first, result.turn, instruction), patch[1])
        else:
            repair = "full"
            instruction = UserMessage(REPAIR_INSTRUCTION.format(errors=listed))
            next_request = request((first, result.turn, instruction), schema)
    try:
        with trace_scope(prompt_version=version, attempt=2, repair=repair):
            second = provider.generate(next_request)
    except ModelProviderError as failure:
        if best is None:
            raise
        repair_error = f"{failure.kind}: {failure.message}"
        kept = StepResult(best, None, repair, triggers, tuple(problems), repair_error)
        return kept, made
    made.append(second)
    try:
        if best is not None and patch is not None:
            candidate = patch[2](best, patch[0].model_validate_json(second.text or ""))
        else:
            candidate = model.model_validate_json(second.text or "")
    except ValidationError as failure:
        if best is None:
            return StepResult(None, summarize_validation(failure), repair, triggers), made
        return StepResult(best, None, repair, triggers, tuple(problems)), made
    return StepResult(candidate, None, repair, triggers, tuple(check(candidate))), made


def _outcome(
    progress: StepwiseProgress,
    draft: DraftBacklogV6 | None,
    error: str | None,
    version: str,
    problems: Sequence[Problem] = (),
) -> DraftOutcome:
    steps = [step for step in (progress.outline, *progress.epics.values()) if step is not None]
    repairs = {step.repair for step in steps}
    repair: RepairKind = (
        "full" if "full" in repairs else "targeted" if "targeted" in repairs else "none"
    )
    results = progress.results
    repair_errors = [step.repair_error for step in steps if step.repair_error]
    return DraftOutcome(
        draft=draft,
        error=error,
        model_id=results[-1].model_id if results else "",
        calls=len(results) + len(repair_errors),
        repaired=draft is not None and not problems and repair != "none",
        repair=repair,
        latency_ms=sum(result.latency_ms for result in results),
        usage=Usage(
            input_tokens=sum(r.usage.input_tokens for r in results),
            output_tokens=sum(r.usage.output_tokens for r in results),
            thinking_tokens=sum(r.usage.thinking_tokens for r in results),
            total_tokens=sum(r.usage.total_tokens for r in results),
        ),
        prompt_version=version,
        check_problems=tuple(problem.message for problem in problems),
        problem_codes=tuple(sorted({problem.code for problem in problems})),
        repair_triggers=tuple(sorted({code for step in steps for code in step.triggers})),
        repair_error=repair_errors[0] if repair_errors else None,
    )


def progress_to_json(progress: StepwiseProgress) -> dict[str, object]:
    """The finished steps, for a run to keep between advances. Usage is not kept: a run counts
    every call as it is made."""
    return {
        "outline": None if progress.outline is None else _step_json(progress.outline),
        "epics": {ref: _step_json(result) for ref, result in progress.epics.items()},
    }


def progress_from_json(data: Mapping[str, object] | None) -> StepwiseProgress:
    """The finished steps a run kept; none for a run that has not started its draft."""
    progress = StepwiseProgress()
    if not data:
        return progress
    outline = data.get("outline")
    if isinstance(outline, Mapping):
        progress.outline = _step_from_json(cast(Mapping[str, Any], outline), DraftOutline)
    epics = data.get("epics")
    if isinstance(epics, Mapping):
        for ref, result in cast(Mapping[str, Any], epics).items():
            progress.epics[ref] = _step_from_json(result, EpicStories)
    return progress


def _step_json[T: BaseModel](result: StepResult[T]) -> dict[str, object]:
    return {
        "output": None if result.output is None else result.output.model_dump(),
        "error": result.error,
        "repair": result.repair,
        "triggers": list(result.triggers),
        "problems": [
            {"code": p.code, "message": p.message, "blocks": list(p.blocks)}
            for p in result.problems
        ],
        "repair_error": result.repair_error,
    }


def _step_from_json[T: BaseModel](data: Mapping[str, Any], model: type[T]) -> StepResult[T]:
    output = data.get("output")
    return StepResult(
        None if output is None else model.model_validate(output),
        data.get("error"),
        cast(RepairKind, data.get("repair") or "none"),
        tuple(data.get("triggers") or ()),
        tuple(
            Problem(cast(ProblemCode, p["code"]), p["message"], tuple(p.get("blocks") or ()))
            for p in data.get("problems") or ()
        ),
        data.get("repair_error"),
    )
