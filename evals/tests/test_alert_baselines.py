import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from scopesteps.evals.alert_baselines import (
    ReportNotFoundError,
    alert_baseline,
    find_report,
    markdown_table,
)

STAMP = "20261101T120000Z"


def _call(seconds: float, reason: str = "completed", variant: str | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "name": "gen_ai.chat",
        "duration_ms": int(seconds * 1000),
        "gen_ai.response.finish_reasons": [reason],
    }
    if variant is not None:
        event["scopesteps.prompt_variant"] = variant
    return event


def _write(directory: Path, name: str, report: dict[str, Any], calls: list[dict[str, Any]]) -> Path:
    path = directory / f"{STAMP}-{name}.json"
    path.write_text(json.dumps({"generated_at": STAMP, **report}))
    path.with_name(f"{STAMP}-{name}.traces.jsonl").write_text(
        "\n".join(json.dumps(call) for call in calls) + "\n"
    )
    return path


def _draft(
    *, error: str | None = None, problems: int = 0, variant: str = "original"
) -> dict[str, Any]:
    return {
        "run_id": "r",
        "variant": variant,
        "error": error,
        "cost_usd_estimate": "0.020000",
        "check_problems": [{"code": "unknown_block"}] * problems,
        "draft": {},
    }


def test_a_sensitivity_report_counts_only_the_adopted_prompt(tmp_path: Path) -> None:
    report = {
        "prompt": "draft-v10",
        "variants": {"original": "draft-v10+abc", "terse": "draft-v10+def"},
        "runs": [
            _draft(error="DRAFT_INVALID", problems=4),
            _draft(),
            _draft(problems=2),
            _draft(error="DRAFT_INVALID", variant="terse"),
        ],
    }
    calls = [
        *(_call(seconds) for seconds in range(1, 20)),
        _call(30, "max_tokens"),
    ]
    calls = [{**call, "scopesteps.prompt_variant": "original"} for call in calls]
    calls.append(_call(90, "max_tokens", variant="terse"))
    path = _write(tmp_path, "sensitivity-draft-v10-model-dev", report, calls)

    baseline = alert_baseline(path)

    assert (baseline.kind, baseline.prompt, baseline.runs, baseline.failed_runs) == (
        "draft",
        "draft-v10+abc",
        3,
        1,
    )
    assert baseline.mean_cost_usd == Decimal("0.02")
    assert baseline.mean_problems == pytest.approx(2.0)
    assert (baseline.calls, baseline.cut_off_calls) == (20, 1)
    assert baseline.p95_call_seconds == 19, "nearest rank: the 19th of 20 calls"


def test_a_change_report_counts_problems_left_in_the_change_set(tmp_path: Path) -> None:
    runs: list[dict[str, Any]] = [
        {
            "run_id": "c1",
            "error": None,
            "cost_usd_estimate": "0.006",
            "problems": [],
            "change_set": {},
        },
        {
            "run_id": "c2",
            "error": None,
            "cost_usd_estimate": "0.008",
            "problems": ["x"],
            "change_set": {},
        },
    ]
    path = _write(
        tmp_path,
        "change-v7-model-dev",
        {"prompt_version": ["explore", "change"], "runs": runs},
        [_call(3)],
    )

    baseline = alert_baseline(path)

    assert (baseline.kind, baseline.prompt) == ("change", "explore, change")
    assert baseline.mean_cost_usd == Decimal("0.007")
    assert baseline.mean_problems == pytest.approx(0.5)


def test_replies_have_no_problem_count(tmp_path: Path) -> None:
    replies = [{"run_id": "q", "error": None, "cost_usd_estimate": "0.001"}]
    path = _write(
        tmp_path, "reply-reply-v4-model-dev", {"prompt_version": "reply-v4", "replies": replies}, []
    )

    baseline = alert_baseline(path)

    assert (baseline.kind, baseline.mean_problems, baseline.p95_call_seconds) == (
        "reply",
        None,
        None,
    )
    assert "| reply | 0/1 (0%-79%) | $0.0010 | n/a | n/a | 0/0 (0%-100%) |" in markdown_table(
        [baseline]
    )


def test_a_held_out_report_is_refused(tmp_path: Path) -> None:
    _write(tmp_path, "agent-model-heldout", {"runs": []}, [])

    with pytest.raises(ReportNotFoundError, match="held-out"):
        find_report(tmp_path, STAMP)


def test_a_missing_report_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ReportNotFoundError, match="found 0"):
        find_report(tmp_path, STAMP)
