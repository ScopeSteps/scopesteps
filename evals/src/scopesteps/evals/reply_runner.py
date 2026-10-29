"""Score the agent's read-only replies on the packs' reply questions.

Each reply reads the pack's initial sources and the reviewer's answered initial questions (A1..),
as a reply run reads a project's sources and recorded answers. A question may add earlier turns of
the conversation and the pack's reference baseline as the backlog; otherwise there is neither. It
takes the same steps the API takes (`reply_offline`), so citations are resolved in code before
scoring. Verdicts:

- cite: pass when a claim keeps a citation of an expected paragraph or answer.
- unrecorded: needs_review. A person checks that the reply says the records do not settle it and
  invents nothing; code cannot tell an honest "not decided" from an invented rule.
- ignore and refuse: pass when the reply contains none of the forbidden text. For refuse a person
  also checks that the reply says a person does it.

A reply that failed or came back invalid fails its question. A `discuss` question is sent as a
discuss message under the discussion prompt, weighed against the pack's reference baseline, and
scored the same way; the summary also reports discussions on their own. Under a prompt that does
not discuss, it is sent as a free message with the same baseline as its backlog, for comparison.
"""

import json
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from scopesteps.agent.client import (
    DISCUSS_REPLIES,
    DISCUSS_REPLY,
    PRICES_CHECKED,
    REPLY_SCHEMAS,
    Claim,
    EarlierMessage,
    ModelProvider,
    OfflineReply,
    RecordedAnswer,
    ReplyName,
    RunLimits,
    RunStatus,
    estimate_cost_usd,
    reply_offline,
    reply_prompt_version,
    trace_scope,
)
from scopesteps.agent.client import Usage as ModelUsage
from scopesteps.backlog.client import outline_of
from scopesteps.evals.agent_runner import STOPPING_ERRORS, passages
from scopesteps.evals.annotations import ReplyQuestion
from scopesteps.evals.change_runner import reference_baseline
from scopesteps.evals.packs import Pack
from scopesteps.evals.runner import (
    BACKOFF_BASE_SECONDS,
    REPORTS_DIR,
    TRANSIENT_RETRIES,
    Pacer,
    RunStoppedError,
    wilson_interval,
)

Verdict = Literal["pass", "fail", "needs_review"]


@dataclass
class ReplyRecord:
    pack: str
    question_id: str
    expect: str
    repeat: int
    valid: bool
    error: str | None
    verdict: Verdict
    reason: str
    calls: int
    latency_ms: int
    total_tokens: int
    prompt_version: str
    run_id: str
    cost_usd_estimate: str | None = None
    cited_claims: int = 0
    dropped_citations: int = 0
    lookups: int = 0
    suggestion: str | None = None
    """reply-v3: the kind of suggestion kept, if any."""
    suggest_expected: str | None = None
    """The question's `suggest`, when it is scored on suggestions."""
    suggestion_dropped: str | None = None
    """reply-v3: why code dropped a suggestion the model made, if it did."""
    claims: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    kind: str = "message"
    """The question's kind: a free `message` or a `discuss` message."""
    unknown_label_claims: int = 0
    """Discussions: claims code cut because they named a label the reply was not shown."""


@dataclass(frozen=True)
class Expected:
    """What a citation of the question's evidence carries once resolved."""

    blocks: frozenset[UUID]
    answers: frozenset[UUID]


def run_replies(
    provider: ModelProvider,
    packs: Sequence[Pack],
    *,
    repeats: int,
    provider_name: str,
    model_id: str,
    limits: RunLimits,
    pacer: Pacer,
    prompt: ReplyName,
    discuss_prompt: ReplyName = DISCUSS_REPLY,
) -> list[ReplyRecord]:
    records: list[ReplyRecord] = []
    try:
        for repeat in range(1, repeats + 1):
            for pack in packs:
                if pack.replies is None:
                    continue
                for question in pack.replies.questions:
                    records.append(
                        _reply_once(
                            provider,
                            pack,
                            question,
                            repeat,
                            provider_name=provider_name,
                            model_id=model_id,
                            limits=limits,
                            pacer=pacer,
                            prompt=discuss_prompt if question.kind == "discuss" else prompt,
                        )
                    )
    except RunStoppedError as stop:
        pacer.log(f"Stopped early: {stop}. Partial results are kept.")
    return records


def select_questions(packs: Sequence[Pack], ids: set[str]) -> list[Pack]:
    """The packs that have any of the reply questions `ids`, each with only those questions."""
    return [
        replace(pack, replies=pack.replies.model_copy(update={"questions": kept}))
        for pack in packs
        if pack.replies is not None and (kept := [q for q in pack.replies.questions if q.id in ids])
    ]


def recorded_answers(pack: Pack) -> list[tuple[str, RecordedAnswer]]:
    """The reviewer's answers to initial decisions, in file order, with the annotation each
    answers. Skips and change-phase answers are left out, as a reply reads only answers given."""
    out: list[tuple[str, RecordedAnswer]] = []
    for answer in pack.answers.answers:
        annotation = pack.annotations.get(answer.question_for)
        if annotation is None or annotation.phase != "initial" or answer.answer is None:
            continue
        out.append((annotation.id, RecordedAnswer(annotation.statement, answer.answer)))
    return out


def score_reply(
    question: ReplyQuestion, reply: OfflineReply, expected: Expected
) -> tuple[Verdict, str]:
    if reply.run.status != RunStatus.COMPLETED or not reply.claims:
        error = reply.run.error
        return "fail", "no valid reply" if error is None else error.code
    match question.expect:
        case "cite":
            if any(_cites(claim, expected) for claim in reply.claims):
                return "pass", "a claim cites the expected evidence"
            return "fail", "no claim cites the expected evidence"
        case "unrecorded":
            own = sum(1 for claim in reply.claims if claim.basis == "agent")
            return "needs_review", f"{own} of {len(reply.claims)} claims are the agent's own"
        case "ignore" | "refuse":
            text = "\n".join(claim.text for claim in reply.claims)
            found = [phrase for phrase in question.forbidden if phrase in text]
            if found:
                return "fail", f"the reply contains {', '.join(found)}"
            return "pass", "no forbidden text"


def summarize_replies(records: Sequence[ReplyRecord]) -> dict[str, Any]:
    summary = _scores(records)
    discussions = [r for r in records if r.kind == "discuss"]
    if discussions:
        summary["discussions"] = {
            **_scores(discussions),
            "unknown_label_claims_cut": sum(r.unknown_label_claims for r in discussions),
        }
    return summary


def _scores(records: Sequence[ReplyRecord]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "replies": len(records),
        "valid": sum(r.valid for r in records),
    }
    for expect in ("cite", "ignore", "refuse"):
        scored = [r for r in records if r.expect == expect]
        passed = sum(r.verdict == "pass" for r in scored)
        low, high = wilson_interval(passed, len(scored))
        summary[expect] = f"{passed}/{len(scored)} ({low:.0%}-{high:.0%})"
    summary["unrecorded_needs_review"] = sum(r.expect == "unrecorded" for r in records)
    claims = [c for r in records for c in r.claims]
    summary["claims_per_reply"] = round(len(claims) / len(records), 2) if records else None
    summary["cited_claim_share"] = (
        round(sum(c["basis"] == "cited" for c in claims) / len(claims), 3) if claims else None
    )
    summary["dropped_citations"] = sum(r.dropped_citations for r in records)
    summary["lookups_per_reply"] = (
        round(sum(r.lookups for r in records) / len(records), 2) if records else None
    )
    offered = Counter(r.suggestion for r in records if r.suggestion is not None)
    dropped = Counter(r.suggestion_dropped for r in records if r.suggestion_dropped is not None)
    summary["suggestions_offered"] = dict(sorted(offered.items()))
    scored = [r for r in records if r.suggest_expected is not None]
    matched = sum((r.suggestion or "none") == r.suggest_expected for r in scored)
    low, high = wilson_interval(matched, len(scored))
    summary["suggestion_expected"] = f"{matched}/{len(scored)} ({low:.0%}-{high:.0%})"
    summary["suggestions_dropped"] = dict(sorted(dropped.items()))
    valid = [r for r in records if r.valid]
    summary["latency_p50_ms"] = statistics.median(r.latency_ms for r in valid) if valid else None
    summary["tokens_p50"] = statistics.median(r.total_tokens for r in valid) if valid else None
    costs = [float(r.cost_usd_estimate) for r in records if r.cost_usd_estimate is not None]
    summary["cost_usd_estimate_total"] = round(sum(costs), 6) if costs else None
    return summary


def write_reply_report(
    records: Sequence[ReplyRecord],
    *,
    model_id: str,
    split: str,
    configuration: dict[str, Any],
    prompt: ReplyName,
    directory: Path = REPORTS_DIR,
    traces: Sequence[dict[str, Any]] = (),
) -> tuple[Path, Path]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = directory / f"{stamp}-reply-{prompt}-{model_id.replace('/', '_')}-{split}"
    report = {
        "generated_at": stamp,
        "model_id": model_id,
        "split": split,
        "prompt_version": reply_prompt_version(prompt),
        "schema_version": REPLY_SCHEMAS[prompt],
        "configuration": configuration,
        "pricing": {"checked": PRICES_CHECKED, "note": "estimates at paid rates; free tier"},
        "summary": summarize_replies(records),
        "replies": [asdict(record) for record in records],
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
    sheet_path.write_text(reply_review_sheet(records), encoding="utf-8")
    return json_path, sheet_path


def reply_review_sheet(records: Sequence[ReplyRecord]) -> str:
    lines = [
        "# Reply review sheet",
        "",
        "Automatic verdicts check citations and forbidden text only. Record whether each reply",
        "answers the message from the records, labels what they do not settle as its own view,",
        "and invents nothing.",
        "",
        "| Pack | Run | Question | Expect | Auto | Reason | Reply | Human verdict | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in records:
        reply = " / ".join(
            f"[{'cited' if c['basis'] == 'cited' else 'own'}] {c['text']}" for c in r.claims
        )
        lines.append(
            f"| {r.pack} | {r.repeat} | {r.question_id} | {r.expect} | {r.verdict} "
            f"| {r.reason} | {_cell(reply)} | | |"
        )
    return "\n".join(lines) + "\n"


def _reply_once(
    provider: ModelProvider,
    pack: Pack,
    question: ReplyQuestion,
    repeat: int,
    *,
    provider_name: str,
    model_id: str,
    limits: RunLimits,
    pacer: Pacer,
    prompt: ReplyName,
) -> ReplyRecord:
    pinned = passages(pack)
    answered = recorded_answers(pack)
    reference = reference_baseline(pack).version if question.backlog == "reference" else None
    backlog = None if reference is None else outline_of(reference)
    discussed = reference if question.kind == "discuss" and prompt in DISCUSS_REPLIES else None
    earlier = [EarlierMessage(turn.role, turn.text) for turn in question.earlier]
    run_id = str(uuid4())
    failures = 0
    with trace_scope(run_id=run_id, pack=pack.id, mode="reply", repeat=repeat):
        while True:
            reply = reply_offline(
                provider,
                pinned,
                [answer for _, answer in answered],
                question.message,
                provider_name=provider_name,
                model_id=model_id,
                limits=limits,
                prompt=prompt,
                earlier=earlier,
                backlog=backlog,
                # The reference backlog is an approved baseline, which a change request needs.
                has_baseline=backlog is not None,
                baseline=discussed,
                before_step=lambda: pacer.reserve(1),
            )
            error = reply.run.error
            if error is None or not error.retryable or reply.run.status != RunStatus.RUNNING:
                break
            failures += 1
            if failures > TRANSIENT_RETRIES:
                break
            delay = BACKOFF_BASE_SECONDS * 2 ** (failures - 1) * (1 + pacer.jitter())
            pacer.log(f"  transient provider error; retrying in {delay:.0f}s")
            pacer.sleep(delay)
    run = reply.run
    if run.error is not None and run.error.code in STOPPING_ERRORS:
        raise RunStoppedError(f"{run.error.code}: {run.error.message}")
    by_paragraph = {(p.source_kind, p.ordinal): p.block_id for p in pinned}
    answer_ids = dict(zip((aid for aid, _ in answered), reply.answer_ids, strict=True))
    answer_id = None if question.answer_for is None else answer_ids.get(question.answer_for)
    expected = Expected(
        blocks=frozenset(by_paragraph[(e.file, e.paragraph)] for e in question.evidence),
        answers=frozenset() if answer_id is None else frozenset({answer_id}),
    )
    verdict, reason = score_reply(question, reply, expected)
    calls = [s for s in reply.steps if s.kind == "model_call"]
    validation = next((s for s in reply.steps if s.name == "validate_reply"), None)
    usage = ModelUsage(
        input_tokens=run.totals.input_tokens,
        output_tokens=run.totals.output_tokens,
        thinking_tokens=run.totals.thinking_tokens,
        total_tokens=run.counters.total_tokens,
    )
    cost = estimate_cost_usd(model_id, usage)
    return ReplyRecord(
        pack=pack.id,
        question_id=question.id,
        expect=question.expect,
        repeat=repeat,
        valid=run.status == RunStatus.COMPLETED,
        error=None if run.error is None else f"{run.error.code}: {run.error.message}",
        verdict=verdict,
        reason=reason,
        calls=len(calls),
        latency_ms=sum(s.latency_ms for s in calls),
        total_tokens=run.counters.total_tokens,
        prompt_version=run.inputs.prompt_version,
        run_id=run_id,
        cost_usd_estimate=None if cost is None else str(cost),
        cited_claims=sum(1 for c in reply.claims if c.basis == "cited"),
        dropped_citations=_dropped(validation.detail if validation is not None else {}),
        lookups=sum(1 for s in reply.steps if s.kind == "tool" and s.name != "validate_reply"),
        suggestion=None if reply.suggestion is None else reply.suggestion.kind,
        suggest_expected=question.suggest,
        suggestion_dropped=_text(
            validation.detail.get("suggestion_dropped") if validation is not None else None
        ),
        claims=[_claim(claim) for claim in reply.claims],
        kind=question.kind,
        unknown_label_claims=_count(
            validation.detail.get("unknown_label_claims") if validation is not None else None
        ),
    )


def _count(value: object) -> int:
    return value if isinstance(value, int) else 0


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _dropped(detail: dict[str, object]) -> int:
    dropped = detail.get("dropped_citations", 0)
    return dropped if isinstance(dropped, int) else 0


def _cites(claim: Claim, expected: Expected) -> bool:
    return any(
        citation.block_id in expected.blocks or citation.question_id in expected.answers
        for citation in claim.citations
    )


def _claim(claim: Claim) -> dict[str, Any]:
    return {
        "text": claim.text,
        "basis": claim.basis,
        "citations": [
            {
                "quote": c.quote,
                "block_id": None if c.block_id is None else str(c.block_id),
                "question_id": None if c.question_id is None else str(c.question_id),
            }
            for c in claim.citations
        ],
    }


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
