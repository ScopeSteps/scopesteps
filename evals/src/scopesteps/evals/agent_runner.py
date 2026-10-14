"""Score full agent runs on the packs: explore, ask the reviewer, then draft (SSPOC-23).

A scripted reviewer answers each question from the pack's clarification answers. A question is
matched to every conflict or missing decision whose evidence it cites. The reviewer answers each
part it has an answer for and says which parts are still undecided, as a person would; if no part
is answered it skips the question. A question that matches none is something the sources already
answer: it is skipped and counted as unneeded, or as a re-ask when it cites an earlier answer or skipped question. The
finished draft is scored with the same rules
as single-pass drafts.
"""

from collections.abc import Sequence
from dataclasses import asdict
from typing import cast
from uuid import uuid4

from scopesteps.agent.client import (
    AGENT_EXPLORE,
    ExploreName,
    ModelProvider,
    Passage,
    Question,
    QuestionStatus,
    RunLimits,
    RunStatus,
    SourceBlockInput,
    estimate_cost_usd,
    parse_draft,
    run_offline,
    trace_scope,
)
from scopesteps.agent.client import Usage as ModelUsage
from scopesteps.evals.annotations import Annotation
from scopesteps.evals.packs import Pack
from scopesteps.evals.runner import (
    BACKOFF_BASE_SECONDS,
    TRANSIENT_RETRIES,
    Pacer,
    RunRecord,
    RunStoppedError,
    score_metrics,
)
from scopesteps.evals.scoring import PackInputs, build_inputs, score_draft
from scopesteps.sources.client import SourceBlockId, SourceVersionId

ASKABLE = frozenset({"conflict", "missing_decision"})
STOPPING_ERRORS = frozenset({"MODEL_QUOTA", "MODEL_AUTH", "MODEL_INVALID_REQUEST"})
"""Provider errors that would fail every later run too, so the evaluation stops (like single-pass)."""
DRAFT_CALLS = 2
"""The most calls one step makes (a draft and its repair), reserved before every step."""


def run_agent(
    provider: ModelProvider,
    packs: Sequence[Pack],
    *,
    repeats: int,
    provider_name: str,
    model_id: str,
    limits: RunLimits,
    max_clarification_rounds: int,
    pacer: Pacer,
    explore: ExploreName = AGENT_EXPLORE,
) -> list[RunRecord]:
    records: list[RunRecord] = []
    try:
        for repeat in range(1, repeats + 1):
            for pack in packs:
                records.append(
                    _run_once(
                        provider,
                        pack,
                        repeat,
                        provider_name=provider_name,
                        model_id=model_id,
                        limits=limits,
                        max_clarification_rounds=max_clarification_rounds,
                        pacer=pacer,
                        explore=explore,
                    )
                )
    except RunStoppedError as stop:
        pacer.log(f"Stopped early: {stop}. Partial results are kept.")
    return records


def passages(pack: Pack) -> list[Passage]:
    """The brief and transcript paragraphs in file order, so labels match `build_inputs` (B1..)."""
    out: list[Passage] = []
    for file in ("brief.md", "transcript.md"):
        version = SourceVersionId(uuid4())
        for block in pack.blocks[file]:
            out.append(Passage(SourceBlockId(uuid4()), version, file, block.ordinal, block.text))
    return out


class ScriptedReviewer:
    """Answers agent questions from the pack, remembering which annotation each one matched."""

    def __init__(self, pack: Pack) -> None:
        self.pack = pack
        initial = build_inputs(pack, "initial")
        self.evidence: dict[str, set[str]] = {
            a.id: {
                initial.block_ids_by_paragraph[(e.file, e.paragraph)]
                for e in a.evidence
                if (e.file, e.paragraph) in initial.block_ids_by_paragraph
            }
            for a in pack.annotations.annotations
            if a.kind in ASKABLE and a.phase == "initial"
        }
        self.answers = {a.question_for: a.answer for a in pack.answers.answers}
        self.matched: dict[str, list[str]] = {}
        """Question id -> the annotations it asked about, most cited evidence first."""

    def overlaps(self, question: Question) -> list[str]:
        """Every askable annotation the question cites evidence of, most overlap first."""
        cited = set(question.block_labels)
        hits = [
            (len(blocks & cited), aid) for aid, blocks in self.evidence.items() if blocks & cited
        ]
        return [aid for _, aid in sorted(hits, key=lambda hit: (-hit[0], hit[1]))]

    def match(self, question: Question) -> Annotation | None:
        """The annotation the question cites most evidence of."""
        hits = self.overlaps(question)
        return self.pack.annotations.get(hits[0]) if hits else None

    def __call__(self, question: Question) -> str | None:
        hits = self.overlaps(question)
        if not hits:
            return None
        self.matched[str(question.id)] = hits
        answered = [text for aid in hits if (text := self.answers.get(aid))]
        if not answered:
            return None
        open_parts = [
            annotation.statement
            for aid in hits
            if not self.answers.get(aid) and (annotation := self.pack.annotations.get(aid))
        ]
        reply = " ".join(answered)
        if open_parts:
            reply += " Not decided yet: " + " ".join(open_parts)
        return reply


def _run_once(
    provider: ModelProvider,
    pack: Pack,
    repeat: int,
    *,
    provider_name: str,
    model_id: str,
    limits: RunLimits,
    max_clarification_rounds: int,
    pacer: Pacer,
    explore: ExploreName,
) -> RunRecord:
    reviewer = ScriptedReviewer(pack)
    run_id = str(uuid4())

    def on_transient(failures: int) -> bool:
        if failures > TRANSIENT_RETRIES:
            return False
        delay = BACKOFF_BASE_SECONDS * 2 ** (failures - 1) * (1 + pacer.jitter())
        pacer.log(f"  transient provider error; retrying in {delay:.0f}s")
        pacer.sleep(delay)
        return True

    with trace_scope(run_id=run_id, pack=pack.id, mode="agent", repeat=repeat):
        result = run_offline(
            provider,
            passages(pack),
            provider_name=provider_name,
            model_id=model_id,
            limits=limits,
            max_clarification_rounds=max_clarification_rounds,
            answer=reviewer,
            before_step=lambda: pacer.reserve(DRAFT_CALLS),
            on_transient=on_transient,
            explore=explore,
        )
    run = result.run
    if run.error is not None and run.error.code in STOPPING_ERRORS and run.draft is None:
        raise RunStoppedError(f"{run.error.code}: {run.error.message}")
    calls = [s for s in result.steps if s.kind == "model_call"]
    usage = ModelUsage(
        input_tokens=run.totals.input_tokens,
        output_tokens=run.totals.output_tokens,
        thinking_tokens=run.totals.thinking_tokens,
        total_tokens=run.counters.total_tokens,
    )
    cost = estimate_cost_usd(model_id, usage)
    validation = next((s for s in reversed(result.steps) if s.name == "validate_backlog"), None)
    detail = validation.detail if validation is not None else {}
    triggers = detail.get("repair_triggers", [])
    record = RunRecord(
        pack=pack.id,
        mode="agent",
        repeat=repeat,
        valid=run.status == RunStatus.READY_FOR_REVIEW and run.draft is not None,
        error=None if run.error is None else f"{run.error.code}: {run.error.message}",
        calls=len(calls),
        repaired=bool(detail.get("repaired", False)),
        latency_ms=sum(s.latency_ms for s in calls),
        total_tokens=run.counters.total_tokens,
        prompt_version=run.inputs.prompt_version,
        repair=str(detail.get("repair", "none")),
        repair_triggers=[str(t) for t in cast(list[object], triggers)]
        if isinstance(triggers, list)
        else [],
        run_id=run_id,
        cost_usd_estimate=None if cost is None else str(cost),
        check_problems=list(run.problems),
    )
    earlier_labels = {q.answer_label for q in result.questions if q.answer_label}
    kinds = {
        str(q.id): "decision"
        if reviewer.matched.get(str(q.id))
        else "re-ask"
        if set(q.block_labels) & earlier_labels
        else "unneeded"
        for q in result.questions
    }
    record.questions = [
        {
            "round": q.round,
            "kind": kinds[str(q.id)],
            "subject": q.subject,
            "question": q.text,
            "cites": list(q.block_labels),
            "matched": reviewer.matched.get(str(q.id), []),
            "reply": q.status.value,
            "label": q.answer_label,
        }
        for q in result.questions
    ]
    if run.draft is None:
        return record
    draft = parse_draft(run.draft)
    inputs = _inputs(pack, result.questions, reviewer)
    card = score_draft(pack, inputs, draft)
    asked = {aid for hits in reviewer.matched.values() for aid in hits}
    needed = set(reviewer.evidence)
    record.metrics = score_metrics(card) | {
        "check_problems": len(run.problems),
        "agent_questions": len(result.questions),
        "agent_questions_unneeded": sum(kind == "unneeded" for kind in kinds.values()),
        "agent_questions_reasked": sum(kind == "re-ask" for kind in kinds.values()),
        "agent_decisions_asked": len(asked & needed),
        "agent_decisions_needed": len(needed),
        "clarification_rounds": run.clarification_rounds,
    }
    record.results = [asdict(r) for r in card.results]
    record.draft = draft.model_dump()
    return record


def _inputs(pack: Pack, questions: Sequence[Question], reviewer: ScriptedReviewer) -> PackInputs:
    """Source blocks plus the agent's own answer (A) and open-decision (U) blocks."""
    base = build_inputs(pack, "initial")
    blocks: list[SourceBlockInput] = list(base.blocks)
    answers: dict[str, str] = {}
    open_decisions: dict[str, str] = {}
    for question in questions:
        if question.answer_label is None:
            continue
        hits = reviewer.matched.get(str(question.id), [])
        if question.status == QuestionStatus.ANSWERED and question.answer is not None:
            blocks.append(
                SourceBlockInput(question.answer_label, "reviewer answer", question.answer)
            )
            # Only the parts the reviewer decided count as answered; an undecided part is still
            # scored as a decision the draft must ask about.
            for aid in hits:
                if reviewer.answers.get(aid):
                    answers.setdefault(aid, question.answer_label)
        else:
            blocks.append(
                SourceBlockInput(
                    question.answer_label,
                    "open decision",
                    f"The reviewer has not answered this yet: {question.text}",
                )
            )
            for aid in hits:
                open_decisions.setdefault(aid, question.answer_label)
    return PackInputs(tuple(blocks), base.block_ids_by_paragraph, answers, open_decisions)
