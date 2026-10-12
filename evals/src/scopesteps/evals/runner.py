"""Single-pass baseline runner: same model configuration, same inputs, repeated runs, scored.

Two modes (POC Implementation Plan, section 14):
- initial: the original brief and transcript only.
- with_answers: the same sources plus the reviewer's final clarification answers, so later
  agent gains are not attributed only to the information the agent asked for.

Until the agent exists, with_answers uses each pack's scripted reviewer answers.
"""

import json
import statistics
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scopesteps.agent.client import (
    DRAFT_PROMPT_VERSION,
    DRAFT_SCHEMA_VERSION,
    ModelProvider,
    ModelProviderError,
    draft_single_pass,
)
from scopesteps.evals.packs import Pack
from scopesteps.evals.scoring import Mode, ScoreCard, build_inputs, score_draft

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"
MAX_VISIBLE_WAIT_SECONDS = 90.0
REPAIR_ATTEMPTS = 1

KIND_GROUPS: dict[str, tuple[str, ...]] = {
    "requirement_coverage": ("confirmed_requirement",),
    "exclusions_and_proposals_respected": ("exclusion", "proposal"),
    "conflicts_and_gaps_handled": ("conflict", "missing_decision"),
    "injection_ignored": ("injection",),
}


class RunStoppedError(Exception):
    """The run cannot continue safely (call cap reached, bad credentials, repeated quota)."""


@dataclass
class Pacer:
    """Keeps requests under the provider's per-minute limit and the run's call cap."""

    requests_per_minute: int
    max_calls: int
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    log: Callable[[str], None] = print
    calls: int = 0
    _last: float | None = None

    def reserve(self, calls: int) -> None:
        if self.calls + calls > self.max_calls:
            raise RunStoppedError(f"call cap of {self.max_calls} reached")
        if self._last is not None:
            wait = 60 / self.requests_per_minute * calls - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self.calls += calls
        self._last = self.clock()


@dataclass
class RunRecord:
    pack: str
    mode: Mode
    repeat: int
    valid: bool
    error: str | None
    calls: int
    repaired: bool
    latency_ms: int
    total_tokens: int
    metrics: dict[str, float | int | None] = field(default_factory=dict[str, float | int | None])
    results: list[dict[str, str]] = field(default_factory=list[dict[str, str]])
    draft: dict[str, Any] | None = None


def run_single_pass(
    provider: ModelProvider,
    packs: Sequence[Pack],
    modes: Sequence[Mode],
    *,
    repeats: int,
    max_output_tokens: int,
    pacer: Pacer,
) -> list[RunRecord]:
    records: list[RunRecord] = []
    try:
        for repeat in range(1, repeats + 1):
            for pack in packs:
                for mode in modes:
                    records.append(
                        _run_once(provider, pack, mode, repeat, max_output_tokens, pacer)
                    )
    except RunStoppedError as stop:
        pacer.log(f"Stopped early: {stop}. Partial results are kept.")
    return records


def _run_once(
    provider: ModelProvider,
    pack: Pack,
    mode: Mode,
    repeat: int,
    max_output_tokens: int,
    pacer: Pacer,
) -> RunRecord:
    inputs = build_inputs(pack, mode)
    for attempt in (1, 2):
        pacer.reserve(REPAIR_ATTEMPTS + 1)
        try:
            outcome = draft_single_pass(
                provider,
                inputs.blocks,
                max_output_tokens=max_output_tokens,
                with_answers=mode == "with_answers",
                repair_attempts=REPAIR_ATTEMPTS,
            )
        except ModelProviderError as error:
            if error.kind == "auth" or error.kind == "invalid_request":
                raise RunStoppedError(f"{error.kind}: {error.message}") from error
            wait = error.retry_after_seconds or 30.0
            if error.kind == "quota" and attempt == 1 and wait <= MAX_VISIBLE_WAIT_SECONDS:
                pacer.log(f"  quota limit hit; waiting {wait:.0f}s, then one more try")
                pacer.sleep(wait)
                continue
            if error.kind == "quota":
                raise RunStoppedError(f"quota: {error.message}") from error
            return RunRecord(
                pack.id, mode, repeat, False, f"{error.kind}: {error.message}", 1, False, 0, 0
            )
        record = RunRecord(
            pack=pack.id,
            mode=mode,
            repeat=repeat,
            valid=outcome.draft is not None,
            error=outcome.error,
            calls=outcome.calls,
            repaired=outcome.repaired,
            latency_ms=outcome.latency_ms,
            total_tokens=outcome.usage.total_tokens,
        )
        if outcome.draft is not None:
            card = score_draft(pack, inputs, outcome.draft)
            record.metrics = _metrics(card)
            record.results = [asdict(result) for result in card.results]
            record.draft = outcome.draft.model_dump()
        return record
    raise RunStoppedError("quota limit persisted after waiting")


def _metrics(card: ScoreCard) -> dict[str, float | int | None]:
    metrics: dict[str, float | int | None] = {
        name: card.rate(kinds) for name, kinds in KIND_GROUPS.items()
    }
    metrics |= {
        "citation_accuracy": card.citation_accuracy,
        "unsupported_commitments": card.unsupported_commitments,
        "proposed_criteria": card.proposed_criteria,
        "items": card.items,
        "questions": card.questions,
    }
    return metrics


def summarize(records: Sequence[RunRecord]) -> dict[str, dict[str, float | int | None]]:
    """Mean of each metric per mode, plus validity, repair and latency figures."""
    summary: dict[str, dict[str, float | int | None]] = {}
    for mode in sorted({record.mode for record in records}):
        runs = [record for record in records if record.mode == mode]
        valid = [record for record in runs if record.valid]
        row: dict[str, float | int | None] = {
            "runs": len(runs),
            "valid_output_rate": len(valid) / len(runs),
            "repaired_runs": sum(record.repaired for record in runs),
        }
        for name in [
            *KIND_GROUPS,
            "citation_accuracy",
            "unsupported_commitments",
            "items",
            "questions",
        ]:
            values = [r.metrics[name] for r in valid if r.metrics.get(name) is not None]
            row[name] = statistics.fmean(v for v in values if v is not None) if values else None
        latencies = sorted(record.latency_ms for record in valid)
        row["latency_p50_s"] = statistics.median(latencies) / 1000 if latencies else None
        row["latency_max_s"] = latencies[-1] / 1000 if latencies else None
        row["tokens_mean"] = statistics.fmean(r.total_tokens for r in valid) if valid else None
        summary[mode] = row
    return summary


def annotation_stability(records: Sequence[RunRecord]) -> dict[str, dict[str, str]]:
    """Pass counts per annotation across repeats, e.g. '2/3', to expose run-to-run variance."""
    table: dict[str, dict[str, list[str]]] = {}
    for record in records:
        for result in record.results:
            key = f"{record.pack}:{result['annotation_id']}"
            table.setdefault(key, {}).setdefault(record.mode, []).append(result["verdict"])
    return {
        key: {
            mode: f"{verdicts.count('pass')}/{len(verdicts)}"
            + (f" ({verdicts.count('needs_review')} review)" if "needs_review" in verdicts else "")
            for mode, verdicts in modes.items()
        }
        for key, modes in table.items()
    }


def write_report(
    records: Sequence[RunRecord],
    *,
    model_id: str,
    split: str,
    configuration: dict[str, Any],
    directory: Path = REPORTS_DIR,
) -> tuple[Path, Path]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = directory / f"{stamp}-single-pass-{model_id}-{split}"
    report = {
        "generated_at": stamp,
        "model_id": model_id,
        "split": split,
        "prompt_version": DRAFT_PROMPT_VERSION,
        "schema_version": DRAFT_SCHEMA_VERSION,
        "configuration": configuration,
        "summary": summarize(records),
        "annotation_stability": annotation_stability(records),
        "runs": [asdict(record) for record in records],
    }
    directory.mkdir(parents=True, exist_ok=True)
    json_path = base.parent / f"{base.name}.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    sheet_path = base.parent / f"{base.name}.review.md"
    sheet_path.write_text(review_sheet(records), encoding="utf-8")
    return json_path, sheet_path


def review_sheet(records: Sequence[RunRecord]) -> str:
    """Human adjudication sheet: automatic verdicts with an empty column for the reviewer."""
    lines = [
        "# Single-pass review sheet",
        "",
        "Automatic verdicts are citation-based. Record whether the draft really handles each",
        "annotation, and note human corrections and the minutes they took.",
        "",
        "| Pack | Mode | Run | Annotation | Expect | Auto | Reason | Human verdict | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        if not record.valid:
            lines.append(
                f"| {record.pack} | {record.mode} | {record.repeat} | (no valid draft) | | fail "
                f"| {record.error} | | |"
            )
        for result in record.results:
            lines.append(
                f"| {record.pack} | {record.mode} | {record.repeat} | {result['annotation_id']} "
                f"| {result['expect']} | {result['verdict']} | {result['reason']} | | |"
            )
    return "\n".join(lines) + "\n"
