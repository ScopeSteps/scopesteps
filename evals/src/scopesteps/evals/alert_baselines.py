"""The figures the production alert thresholds are set from (ops/monitoring/alerts.yaml, ADR 0023).

Reads a recorded report and its traces from `reports/` and computes, for the run kind it measured,
what the alert rules watch in production: the share of failed runs, the mean estimated cost and
problems left per run, the p95 model-call latency and the share of calls cut off by the output
limit. No model is called. A sensitivity report counts only its `original` variant, the prompt
as adopted.
"""

import json
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from scopesteps.evals.runner import wilson_interval


@dataclass(frozen=True)
class AlertBaseline:
    stamp: str
    prompt: str
    kind: str
    """draft, change or reply: the `scopesteps.run.kind` the production rules filter on."""
    runs: int
    failed_runs: int
    mean_cost_usd: Decimal
    mean_problems: float | None
    """None for replies, which are not checked."""
    calls: int
    p95_call_seconds: float | None
    cut_off_calls: int

    @property
    def failure_ci95(self) -> tuple[float, float]:
        return wilson_interval(self.failed_runs, self.runs)

    @property
    def cut_off_ci95(self) -> tuple[float, float]:
        return wilson_interval(self.cut_off_calls, self.calls)


class ReportNotFoundError(Exception):
    pass


def find_report(directory: Path, stamp: str) -> Path:
    """The report JSON for a stamp; review sheets and traces share the stamp but not the suffix."""
    matches = sorted(
        path
        for path in directory.glob(f"{stamp}-*.json")
        if not path.name.endswith(".traces.jsonl")
    )
    if len(matches) != 1:
        raise ReportNotFoundError(
            f"Expected one report for {stamp} in {directory}, found {len(matches)}"
        )
    if matches[0].name.endswith("-heldout.json"):
        # Thresholds are set from dev runs only: the held-out packs stay blind (ADR 0017).
        raise ReportNotFoundError(f"{matches[0].name} is a held-out report")
    return matches[0]


def alert_baseline(report_path: Path) -> AlertBaseline:
    report = cast(dict[str, Any], json.loads(report_path.read_text()))
    traces_path = report_path.with_name(report_path.name.removesuffix(".json") + ".traces.jsonl")
    traces = (
        [
            cast(dict[str, Any], json.loads(line))
            for line in traces_path.read_text().splitlines()
            if line
        ]
        if traces_path.exists()
        else []
    )
    if "replies" in report:
        kind, records = "reply", cast(list[dict[str, Any]], report["replies"])
    else:
        records = [
            record
            for record in cast(list[dict[str, Any]], report["runs"])
            if record.get("variant", "original") == "original"
        ]
        kind = "change" if records and "change_set" in records[0] else "draft"
    # Trace run ids are the runner's, not the records', so a variant is told apart by its label.
    calls = [
        event
        for event in traces
        if event.get("scopesteps.prompt_variant", "original") == "original"
    ]
    durations = sorted(int(event.get("duration_ms") or 0) / 1000 for event in calls)
    variants = cast(dict[str, str], report.get("variants") or {})
    prompt = variants.get("original") or report.get("prompt_version") or ""
    return AlertBaseline(
        stamp=str(report["generated_at"]),
        prompt=", ".join(cast(list[str], prompt)) if isinstance(prompt, list) else str(prompt),
        kind=kind,
        runs=len(records),
        failed_runs=sum(1 for record in records if record.get("error")),
        mean_cost_usd=_mean_cost(records),
        mean_problems=None if kind == "reply" else _mean_problems(records, kind),
        calls=len(calls),
        p95_call_seconds=_nearest_rank(durations, 0.95),
        cut_off_calls=sum(
            1
            for event in calls
            if "max_tokens" in (event.get("gen_ai.response.finish_reasons") or [])
        ),
    )


def _mean_cost(records: list[dict[str, Any]]) -> Decimal:
    if not records:
        return Decimal(0)
    total = sum(
        (Decimal(str(record.get("cost_usd_estimate") or 0)) for record in records), Decimal(0)
    )
    return total / len(records)


def _mean_problems(records: list[dict[str, Any]], kind: str) -> float:
    key = "check_problems" if kind == "draft" else "problems"
    if not records:
        return 0.0
    return sum(len(cast(list[object], record.get(key) or [])) for record in records) / len(records)


def _nearest_rank(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    return values[max(0, math.ceil(quantile * len(values)) - 1)]


def markdown_table(baselines: list[AlertBaseline]) -> str:
    """The table `evals/README.md` records under "Alert thresholds"."""
    lines = [
        "| Report | Prompt | Kind | Failed runs | Mean cost per run | Mean problems left "
        "| p95 call latency | Calls cut off |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for baseline in baselines:
        fail_low, fail_high = baseline.failure_ci95
        cut_low, cut_high = baseline.cut_off_ci95
        problems = "n/a" if baseline.mean_problems is None else f"{baseline.mean_problems:.2f}"
        latency = (
            "n/a" if baseline.p95_call_seconds is None else f"{baseline.p95_call_seconds:.1f} s"
        )
        lines.append(
            f"| `{baseline.stamp}` | `{baseline.prompt}` | {baseline.kind} "
            f"| {baseline.failed_runs}/{baseline.runs} ({fail_low:.0%}-{fail_high:.0%}) "
            f"| ${baseline.mean_cost_usd:.4f} | {problems} | {latency} "
            f"| {baseline.cut_off_calls}/{baseline.calls} ({cut_low:.0%}-{cut_high:.0%}) |"
        )
    return "\n".join(lines)
