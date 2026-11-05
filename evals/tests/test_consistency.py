"""Consistency scores on fixed, synthetic example reports, worked out by hand (SSPOC-134)."""

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from scopesteps.evals.cli import main
from scopesteps.evals.consistency import Range, Requirements, add_consistency, consistency

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/consistency"


def _report(name: str) -> dict[str, Any]:
    report: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return report


def test_requirements_are_found_in_every_some_or_no_repeats_per_pack() -> None:
    scores = consistency(_report("single-pass-report.json"))

    by_group = {group.group: group for group in scores.groups}
    pack_a = by_group["pack-a · without_answers"]
    pack_b = by_group["pack-b · without_answers"]
    # The third repeat of pack-a produced no valid draft, so it found nothing.
    assert (pack_a.repeats, pack_a.valid_repeats) == (3, 2)
    assert pack_a.requirements == Requirements(expected=3, every=0, some=2, none=1)
    assert pack_b.requirements == Requirements(expected=2, every=1, some=1, none=0)
    assert Requirements(2, 1, 1, 0).share(1) == 0.5


def test_story_counts_and_problems_left_vary_between_valid_repeats() -> None:
    scores = consistency(_report("single-pass-report.json"))

    by_group = {group.group: group for group in scores.groups}
    assert by_group["pack-a · without_answers"].stories == Range(3, 5)
    assert by_group["pack-a · without_answers"].problems == Range(0, 2)
    assert by_group["pack-b · without_answers"].stories == Range(4, 4)
    assert by_group["pack-b · without_answers"].problems == Range(1, 1)


def test_pass_in_every_repeat_is_stricter_than_the_mean_pass_rate() -> None:
    scores = consistency(_report("single-pass-report.json"))

    rows = {(m.scope, m.metric): m for m in scores.metrics}
    coverage = rows[("without_answers", "requirement_coverage")]
    # Only CR-10 passes in all three repeats; a needs_review verdict counts as no pass.
    assert (coverage.items, coverage.pass_every) == (5, 1)
    assert coverage.pass_every_rate == pytest.approx(0.2)
    assert coverage.mean_pass_rate == pytest.approx((2 / 3 + 1 / 3 + 0 + 1 + 1 / 3) / 5)
    exclusions = rows[("without_answers", "exclusions_and_proposals_respected")]
    assert (exclusions.items, exclusions.pass_every) == (1, 0)
    assert rows[("all", "requirement_coverage")] == coverage.__class__(
        "all", "requirement_coverage", 5, 1, coverage.mean_pass_rate
    )


def test_change_and_reply_reports_get_pass_in_every_repeat_once_each() -> None:
    change = consistency(_report("change-report.json"))
    replies = consistency(_report("reply-report.json"))

    assert [(m.scope, m.metric, m.items, m.pass_every) for m in change.metrics] == [
        ("all", "change_impacts", 2, 1)
    ]
    assert change.metrics[0].mean_pass_rate == pytest.approx(0.75)
    assert change.groups[0].problems == Range(0, 1)
    assert change.groups[0].stories is None
    assert [(m.metric, m.items, m.pass_every) for m in replies.metrics] == [("reply_answers", 2, 1)]


def test_the_command_adds_the_scores_to_a_saved_report_without_a_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "20261104T000000Z-single-pass-synthetic-model-dev.json"
    shutil.copy(FIXTURES / "single-pass-report.json", report)
    monkeypatch.setattr(sys, "argv", ["scopesteps-evals", "consistency", str(report)])

    with pytest.raises(SystemExit) as exited:
        main()

    assert exited.value.code == 0
    printed = capsys.readouterr().out

    saved = json.loads(report.read_text())["consistency"]
    assert saved == consistency(_report("single-pass-report.json")).as_json()
    assert saved["groups"][0]["requirements"]["none_share"] == pytest.approx(1 / 3)
    assert "| pack-a · without_answers | 3 (2) | 3 | 0% | 67% | 33% |" in printed


def test_recomputing_gives_the_same_scores(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    shutil.copy(FIXTURES / "change-report.json", report)

    first = add_consistency(report)
    second = add_consistency(report)

    assert first == second


def test_a_sensitivity_report_is_scored_per_variant_and_never_pooled() -> None:
    report = _report("single-pass-report.json")
    report["runs"] = [{"variant": "original"} | run for run in report["runs"]] + [
        {"variant": "terse"} | run for run in report["runs"]
    ]

    scores = consistency(report)

    assert {m.scope for m in scores.metrics} == {
        "original · without_answers",
        "terse · without_answers",
    }
    assert "original · pack-a · without_answers" in {group.group for group in scores.groups}
