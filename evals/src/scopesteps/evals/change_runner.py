"""Score change analysis on the packs' change requests against a reference baseline.

The baseline is built from the pack's answer key, not drafted by a model, so a change run is
measured on its own and not on the quality of an earlier draft: one epic, a story per confirmed
requirement (requirements past the story ceiling become further criteria of the last story), the
pack's exclusions and proposals as out-of-scope notes, and its answered initial decisions. The
run is `analyze_change_offline`, the same steps a change run takes in the API; a scripted
reviewer answers its questions from the pack's change-phase answers.

Each `expected_change_impact` annotation gets a verdict:

- ask, about an exclusion: pass when a scope decision reverses that exclusion.
- ask, otherwise: pass when a question of the run or of the change set cites its evidence.
- add: pass when an added item cites its evidence.
- modify / remove: pass when every related requirement's story is modified / removed.
- unchanged: pass when no related story is touched and no related exclusion is reversed.

A run that ends without a change set fails every impact. Whether a citation really supports an
operation is for a person on the review sheet.
"""

import json
import statistics
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from scopesteps.agent.client import (
    CHANGE_PROMPT_VERSION,
    CHANGE_REQUEST_KIND,
    CHANGE_SCHEMA_VERSION,
    PRICES_CHECKED,
    BaselineLabels,
    ChangeSetOutput,
    ModelProvider,
    OfflineChange,
    Passage,
    Question,
    RunLimits,
    RunStatus,
    analyze_change_offline,
    estimate_cost_usd,
    trace_scope,
)
from scopesteps.agent.client import Usage as ModelUsage
from scopesteps.backlog.client import (
    MAX_STORIES,
    BacklogVersion,
    BacklogVersionId,
    Criterion,
    CriterionId,
    Decision,
    DecisionId,
    Evidence,
    Item,
    ItemId,
    ScopeNote,
    VersionState,
)
from scopesteps.evals.agent_runner import STOPPING_ERRORS, passages
from scopesteps.evals.annotations import Annotation, SourceFile
from scopesteps.evals.packs import CHANGE_REQUEST_FILE, Pack
from scopesteps.evals.runner import (
    BACKOFF_BASE_SECONDS,
    REPORTS_DIR,
    TRANSIENT_RETRIES,
    Pacer,
    RunStoppedError,
    wilson_interval,
)
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceBlockId, SourceVersionId

Verdict = Literal["pass", "fail", "needs_review"]
DRAFT_CALLS = 2
"""The most calls one step makes (a change set and its repair), reserved before every step."""
NOW = datetime(2026, 10, 14, tzinfo=UTC)


@dataclass(frozen=True)
class ReferenceBaseline:
    version: BacklogVersion
    passages: tuple[Passage, ...]
    """The initial sources' paragraphs, then the change request's, as a change run pins them."""
    stories: dict[str, ItemId]
    """Confirmed-requirement annotation id -> the story that carries it."""
    exclusions: dict[str, int]
    """Exclusion annotation id -> its position in the baseline's out_of_scope."""


def reference_baseline(pack: Pack) -> ReferenceBaseline:
    initial = passages(pack)
    request_version = SourceVersionId(uuid4())
    request = [
        Passage(SourceBlockId(uuid4()), request_version, CHANGE_REQUEST_KIND, b.ordinal, b.text)
        for b in pack.blocks[CHANGE_REQUEST_FILE]
    ]
    by_paragraph = {(p.source_kind, p.ordinal): p for p in initial}

    def evidence(annotation: Annotation) -> tuple[Evidence, ...]:
        return tuple(
            Evidence(passage.source_version_id, passage.block_id, e.quote)
            for e in annotation.evidence
            if (passage := by_paragraph.get((e.file, e.paragraph))) is not None
        )

    epic = Item(ItemId(uuid4()), "epic", None, pack.annotations.pack.title, "The project scope.")
    items: list[Item] = [epic]
    stories: dict[str, ItemId] = {}
    for annotation in pack.annotations.annotations:
        if annotation.kind != "confirmed_requirement":
            continue
        criterion = Criterion(
            CriterionId(uuid4()), annotation.statement, "source", evidence(annotation)
        )
        if len(items) - 1 < MAX_STORIES:
            story = Item(
                ItemId(uuid4()),
                "story",
                epic.id,
                annotation.statement[:200],
                annotation.statement,
                criteria=(criterion,),
            )
            items.append(story)
        else:
            last = items[-1]
            story = Item(
                last.id,
                last.kind,
                last.parent_id,
                last.title,
                last.description,
                criteria=(*last.criteria, criterion),
            )
            items[-1] = story
        stories[annotation.id] = story.id
    notes: list[ScopeNote] = []
    exclusions: dict[str, int] = {}
    for annotation in pack.annotations.annotations:
        if annotation.kind in {"exclusion", "proposal"}:
            if annotation.kind == "exclusion":
                exclusions[annotation.id] = len(notes)
            notes.append(
                ScopeNote(
                    "excluded" if annotation.kind == "exclusion" else "suggested",
                    annotation.statement,
                    evidence(annotation),
                )
            )
    answers = {a.question_for: a for a in pack.answers.answers if a.answer is not None}
    decisions = tuple(
        Decision(
            id=DecisionId(uuid4()),
            kind="conflict" if annotation.kind == "conflict" else "missing_decision",
            status="answered",
            subject=annotation.statement[:200],
            question=annotation.statement,
            why_it_matters="Recorded in the baseline.",
            evidence=evidence(annotation),
            answer=answers[annotation.id].answer,
            decided_by=UserId(uuid4()),
            decided_at=NOW,
        )
        for annotation in pack.annotations.annotations
        if annotation.phase == "initial" and annotation.id in answers
    )
    version = BacklogVersion(
        id=BacklogVersionId(uuid4()),
        project_id=ProjectId(uuid4()),
        base_version_id=None,
        revision=1,
        state=VersionState.APPROVED,
        content_hash=uuid4().hex * 2,
        run_id=None,
        source_version_ids=tuple(dict.fromkeys(p.source_version_id for p in initial)),
        items=tuple(items),
        decisions=decisions,
        out_of_scope=tuple(notes),
        created_by=UserId(uuid4()),
        created_at=NOW,
    )
    return ReferenceBaseline(version, (*initial, *request), stories, exclusions)


def block_labels(baseline: ReferenceBaseline) -> dict[tuple[SourceFile, int], str]:
    """(file, paragraph) -> the B label a change run gives that paragraph."""
    labels: dict[tuple[SourceFile, int], str] = {}
    for index, passage in enumerate(baseline.passages, start=1):
        file = (
            CHANGE_REQUEST_FILE
            if passage.source_kind == CHANGE_REQUEST_KIND
            else passage.source_kind
        )
        labels[(file, passage.ordinal)] = f"B{index}"
    return labels


class ChangeReviewer:
    """Answers a change run's questions from the pack's change-phase answers, by the evidence a
    question cites; a question that matches no change impact, or one with no answer, is
    skipped."""

    def __init__(self, pack: Pack, labels: dict[tuple[SourceFile, int], str]) -> None:
        answers = {a.question_for: a.answer for a in pack.answers.answers}
        self.evidence = {
            a.id: {
                labels[(e.file, e.paragraph)] for e in a.evidence if (e.file, e.paragraph) in labels
            }
            for a in pack.annotations.annotations
            if a.phase == "change" and a.expect == "ask"
        }
        self.answers = {aid: text for aid, text in answers.items() if aid in self.evidence}
        self.matched: dict[str, list[str]] = {}

    def __call__(self, question: Question) -> str | None:
        cited = set(question.block_labels)
        hits = sorted(
            (aid for aid, blocks in self.evidence.items() if blocks & cited),
            key=lambda aid: -len(self.evidence[aid] & cited),
        )
        self.matched[str(question.id)] = hits
        replies = [text for aid in hits if (text := self.answers.get(aid))]
        return " ".join(replies) if replies else None


@dataclass
class ChangeRecord:
    pack: str
    repeat: int
    valid: bool
    error: str | None
    outcome: str | None
    calls: int
    latency_ms: int
    total_tokens: int
    prompt_version: str
    run_id: str
    repaired: bool = False
    repair_triggers: list[str] = field(default_factory=list[str])
    cost_usd_estimate: str | None = None
    problems: list[str] = field(default_factory=list[str])
    results: list[dict[str, str]] = field(default_factory=list[dict[str, str]])
    unintended_edits: int = 0
    questions: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    change_set: dict[str, Any] | None = None


def run_changes(
    provider: ModelProvider,
    packs: Sequence[Pack],
    *,
    repeats: int,
    provider_name: str,
    model_id: str,
    limits: RunLimits,
    max_clarification_rounds: int,
    pacer: Pacer,
) -> list[ChangeRecord]:
    records: list[ChangeRecord] = []
    try:
        for repeat in range(1, repeats + 1):
            for pack in packs:
                records.append(
                    _change_once(
                        provider,
                        pack,
                        repeat,
                        provider_name=provider_name,
                        model_id=model_id,
                        limits=limits,
                        max_clarification_rounds=max_clarification_rounds,
                        pacer=pacer,
                    )
                )
    except RunStoppedError as stop:
        pacer.log(f"Stopped early: {stop}. Partial results are kept.")
    return records


def score_change(
    pack: Pack,
    baseline: ReferenceBaseline,
    result: OfflineChange,
    labels: dict[tuple[SourceFile, int], str],
) -> tuple[list[dict[str, str]], int]:
    """A verdict per change impact, and how many baseline stories the change set touched that no
    impact expects to change."""
    impacts = [a for a in pack.annotations.annotations if a.phase == "change"]
    output = _output(result)
    if output is None:
        return [_verdict(a, "fail", "no valid change set") for a in impacts], 0
    shown = result.labels
    story_label = {aid: _label(shown, item_id) for aid, item_id in baseline.stories.items()}
    exclusion_label = {
        aid: next((x for x, position in shown.exclusions.items() if position == p), None)
        for aid, p in baseline.exclusions.items()
    }
    touched = {op.op: set[str]() for op in output.operations}
    for op in output.operations:
        touched[op.op].add(op.item)
    modified, removed = touched.get("modify_item", set()), touched.get("remove_item", set())
    reversed_labels = {d.reverses for d in output.scope_decisions}
    asked = [set(q.block_labels) for q in result.questions] + [
        {c.block_id for c in q.citations} for q in output.questions
    ]
    added = [
        {c.block_id for c in [*op.citations, *(c for cr in op.add_criteria for c in cr.citations)]}
        for op in output.operations
        if op.op == "add_item"
    ]
    verdicts: list[dict[str, str]] = []
    expected_touched: set[str] = set()
    for impact in impacts:
        evidence = {
            labels[(e.file, e.paragraph)]
            for e in impact.evidence
            if (e.file, e.paragraph) in labels
        }
        related_stories = {s for r in impact.relates_to if (s := story_label.get(r))}
        related_exclusions = {x for r in impact.relates_to if (x := exclusion_label.get(r))}
        if impact.expect in {"modify", "remove", "ask"}:
            expected_touched |= related_stories
        match impact.expect:
            case "ask" if related_exclusions:
                ok = bool(related_exclusions & reversed_labels)
                verdicts.append(_verdict(impact, ok, "a scope decision reverses the exclusion"))
            case "ask":
                ok = any(blocks & evidence for blocks in asked)
                verdicts.append(_verdict(impact, ok, "a question cites the evidence"))
            case "add":
                ok = any(blocks & evidence for blocks in added)
                verdicts.append(_verdict(impact, ok, "an added item cites the evidence"))
            case "modify" | "remove":
                done = modified if impact.expect == "modify" else removed
                if not related_stories:
                    verdicts.append(_verdict(impact, "needs_review", "no related story"))
                else:
                    ok = related_stories <= done
                    verdicts.append(
                        _verdict(impact, ok, f"every related story is {impact.expect}d")
                    )
            case _:
                ok = not (related_stories & (modified | removed)) and not (
                    related_exclusions & reversed_labels
                )
                verdicts.append(_verdict(impact, ok, "related work is untouched"))
    unintended = len(((modified | removed) & set(shown.stories)) - expected_touched)
    return verdicts, unintended


def summarize_changes(records: Sequence[ChangeRecord]) -> dict[str, Any]:
    summary: dict[str, Any] = {"runs": len(records), "valid": sum(r.valid for r in records)}
    for expect in ("ask", "add", "modify", "remove", "unchanged"):
        scored = [v for r in records for v in r.results if v["expect"] == expect]
        if not scored:
            continue
        passed = sum(v["verdict"] == "pass" for v in scored)
        low, high = wilson_interval(passed, len(scored))
        summary[expect] = f"{passed}/{len(scored)} ({low:.0%}-{high:.0%})"
    summary["unintended_edits"] = sum(r.unintended_edits for r in records)
    summary["repaired"] = sum(r.repaired for r in records)
    valid = [r for r in records if r.valid]
    summary["latency_p50_ms"] = statistics.median(r.latency_ms for r in valid) if valid else None
    summary["tokens_p50"] = statistics.median(r.total_tokens for r in valid) if valid else None
    costs = [float(r.cost_usd_estimate) for r in records if r.cost_usd_estimate is not None]
    summary["cost_usd_estimate_total"] = round(sum(costs), 6) if costs else None
    return summary


def write_change_report(
    records: Sequence[ChangeRecord],
    *,
    model_id: str,
    split: str,
    configuration: dict[str, Any],
    directory: Path = REPORTS_DIR,
    traces: Sequence[dict[str, Any]] = (),
) -> tuple[Path, Path]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = directory / f"{stamp}-change-{model_id.replace('/', '_')}-{split}"
    report = {
        "generated_at": stamp,
        "model_id": model_id,
        "split": split,
        "prompt_version": CHANGE_PROMPT_VERSION,
        "schema_version": CHANGE_SCHEMA_VERSION,
        "configuration": configuration,
        "pricing": {"checked": PRICES_CHECKED, "note": "estimates at paid rates; free tier"},
        "summary": summarize_changes(records),
        "runs": [asdict(record) for record in records],
    }
    directory.mkdir(parents=True, exist_ok=True)
    json_path = base.parent / f"{base.name}.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if traces:
        trace_path = base.parent / f"{base.name}.traces.jsonl"
        trace_path.write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in traces),
            encoding="utf-8",
        )
    sheet_path = base.parent / f"{base.name}.review.md"
    sheet_path.write_text(change_review_sheet(records), encoding="utf-8")
    return json_path, sheet_path


def change_review_sheet(records: Sequence[ChangeRecord]) -> str:
    lines = [
        "# Change analysis review sheet",
        "",
        "Automatic verdicts check ids and citations only. Record whether each operation does",
        "what the request asks, cites what supports it, and leaves unrelated work alone.",
        "",
        "| Pack | Run | Impact | Expect | Auto | Reason | Human verdict | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        for result in record.results:
            lines.append(
                f"| {record.pack} | {record.repeat} | {result['annotation_id']} "
                f"| {result['expect']} | {result['verdict']} | {result['reason']} | | |"
            )
    return "\n".join(lines) + "\n"


def _change_once(
    provider: ModelProvider,
    pack: Pack,
    repeat: int,
    *,
    provider_name: str,
    model_id: str,
    limits: RunLimits,
    max_clarification_rounds: int,
    pacer: Pacer,
) -> ChangeRecord:
    baseline = reference_baseline(pack)
    labels = block_labels(baseline)
    reviewer = ChangeReviewer(pack, labels)
    run_id = str(uuid4())
    with trace_scope(run_id=run_id, pack=pack.id, mode="change", repeat=repeat):
        result = analyze_change_offline(
            provider,
            baseline.passages,
            baseline.version,
            provider_name=provider_name,
            model_id=model_id,
            limits=limits,
            max_clarification_rounds=max_clarification_rounds,
            answer=reviewer,
            before_step=lambda: pacer.reserve(DRAFT_CALLS),
            on_transient=_on_transient(pacer),
        )
    run = result.run
    if run.error is not None and run.error.code in STOPPING_ERRORS and run.draft is None:
        raise RunStoppedError(f"{run.error.code}: {run.error.message}")
    calls = [s for s in result.steps if s.kind == "model_call"]
    validation = next((s for s in reversed(result.steps) if s.name == "validate_change"), None)
    detail = {} if validation is None else validation.detail
    triggers = detail.get("repair_triggers", [])
    usage = ModelUsage(
        input_tokens=run.totals.input_tokens,
        output_tokens=run.totals.output_tokens,
        thinking_tokens=run.totals.thinking_tokens,
        total_tokens=run.counters.total_tokens,
    )
    cost = estimate_cost_usd(model_id, usage)
    verdicts, unintended = score_change(pack, baseline, result, labels)
    return ChangeRecord(
        pack=pack.id,
        repeat=repeat,
        valid=run.status in {RunStatus.READY_FOR_REVIEW, RunStatus.COMPLETED},
        error=None if run.error is None else f"{run.error.code}: {run.error.message}",
        outcome=None if result.change is None else result.change.outcome,
        calls=len(calls),
        latency_ms=sum(s.latency_ms for s in calls),
        total_tokens=run.counters.total_tokens,
        prompt_version=run.inputs.prompt_version,
        run_id=run_id,
        repaired=bool(detail.get("repaired", False)),
        repair_triggers=[str(t) for t in cast(list[object], triggers)]
        if isinstance(triggers, list)
        else [],
        cost_usd_estimate=None if cost is None else str(cost),
        problems=list(run.problems),
        results=verdicts,
        unintended_edits=unintended,
        questions=[
            {
                "question": q.text,
                "cites": list(q.block_labels),
                "matched": reviewer.matched.get(str(q.id), []),
                "reply": q.status.value,
            }
            for q in result.questions
        ],
        change_set=run.draft,
    )


def _on_transient(pacer: Pacer) -> Callable[[int], bool]:
    def retry(failures: int) -> bool:
        if failures > TRANSIENT_RETRIES:
            return False
        delay = BACKOFF_BASE_SECONDS * 2 ** (failures - 1) * (1 + pacer.jitter())
        pacer.log(f"  transient provider error; retrying in {delay:.0f}s")
        pacer.sleep(delay)
        return True

    return retry


def _output(result: OfflineChange) -> ChangeSetOutput | None:
    if result.change is None or result.run.draft is None:
        return None
    return ChangeSetOutput.model_validate(result.run.draft)


def _label(labels: BaselineLabels, item_id: UUID) -> str | None:
    return labels.item_label(item_id)


def _verdict(annotation: Annotation, outcome: bool | Verdict, reason: str) -> dict[str, str]:
    verdict: Verdict = outcome if isinstance(outcome, str) else ("pass" if outcome else "fail")
    return {
        "annotation_id": annotation.id,
        "expect": annotation.expect,
        "verdict": verdict,
        "reason": reason if verdict != "fail" else f"not met: {reason}",
    }
