import json
import sys
from pathlib import Path

import pytest

from scopesteps.agent.client import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    Usage,
)
from scopesteps.evals import cli
from scopesteps.evals.packs import DATASETS_DIR, Pack, load_pack
from scopesteps.evals.runner import (
    DraftSettings,
    Pacer,
    annotation_stability,
    rescore_report,
    review_sheet,
    run_single_pass,
    summarize,
    wilson_interval,
    write_report,
)

NO_CHECKS = DraftSettings(run_checks=False)
EMPTY_DRAFT = json.dumps({"statements": [], "items": [], "questions": []})


class FakeProvider:
    def __init__(self, script: list[ModelResult | ModelProviderError]) -> None:
        self.script = script
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        step = self.script.pop(0)
        if isinstance(step, ModelProviderError):
            raise step
        return step


def _ok(text: str = EMPTY_DRAFT) -> ModelResult:
    return ModelResult(
        "test", "m", ModelTurn(()), text, (), "completed", Usage(total_tokens=7), 100
    )


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def _pacer(clock: Clock, max_calls: int = 40) -> Pacer:
    return Pacer(
        15, max_calls, sleep=clock.sleep, clock=clock, log=lambda _: None, jitter=lambda: 0.0
    )


@pytest.fixture(scope="module")
def campus() -> Pack:
    return load_pack(DATASETS_DIR / "dev" / "campus-room-booking", "dev")


def test_runs_every_pack_mode_and_repeat_with_pacing(campus: Pack) -> None:
    clock = Clock()
    provider = FakeProvider([_ok() for _ in range(4)])

    records = run_single_pass(
        provider,
        [campus],
        ["initial", "with_answers"],
        repeats=2,
        max_output_tokens=10,
        pacer=_pacer(clock),
        settings=NO_CHECKS,
    )

    assert [(r.mode, r.repeat, r.valid) for r in records] == [
        ("initial", 1, True),
        ("with_answers", 1, True),
        ("initial", 2, True),
        ("with_answers", 2, True),
    ]
    assert clock.sleeps == [8.0, 8.0, 8.0], "two reserved calls at 15/min need 8 s spacing"
    summary = summarize(records)
    assert summary["initial"]["valid_output_rate"] == 1
    assert summary["initial"]["requirement_coverage"] == 0
    assert annotation_stability(records)["campus-room-booking:CR-01"] == {
        "initial": "0/2",
        "with_answers": "0/2",
    }


def test_quota_errors_wait_visibly_and_try_once_more(campus: Pack) -> None:
    clock = Clock()
    quota = ModelProviderError("quota", "limit", retry_after_seconds=17)
    provider = FakeProvider([quota, _ok()])

    records = run_single_pass(
        provider,
        [campus],
        ["initial"],
        repeats=1,
        max_output_tokens=10,
        pacer=_pacer(clock),
        settings=NO_CHECKS,
    )

    assert records[0].valid
    assert 17 in clock.sleeps


@pytest.mark.parametrize(
    "error",
    [
        ModelProviderError("quota", "limit", retry_after_seconds=3600),
        ModelProviderError("auth", "bad key"),
        ModelProviderError("invalid_request", "bad schema"),
    ],
)
def test_unrecoverable_errors_stop_the_run_and_keep_partial_results(
    campus: Pack, error: ModelProviderError
) -> None:
    provider = FakeProvider([_ok(), error])

    records = run_single_pass(
        provider,
        [campus],
        ["initial", "with_answers"],
        repeats=1,
        max_output_tokens=10,
        pacer=_pacer(Clock()),
        settings=NO_CHECKS,
    )

    assert [r.mode for r in records] == ["initial"]


def test_overload_is_retried_with_exponential_backoff(campus: Pack) -> None:
    clock = Clock()
    overloaded = ModelProviderError("unavailable", "503")
    provider = FakeProvider([overloaded, overloaded, _ok()])

    records = run_single_pass(
        provider,
        [campus],
        ["initial"],
        repeats=1,
        max_output_tokens=10,
        pacer=_pacer(clock),
        settings=NO_CHECKS,
    )

    assert records[0].valid
    assert clock.sleeps == [4.0, 4.0, 8.0], "backoff 4 s, pacing tops up to 8 s, backoff 8 s"


def test_transient_errors_are_recorded_after_retries_and_the_run_continues(campus: Pack) -> None:
    slow = ModelProviderError("timeout", "slow")
    provider = FakeProvider([slow, slow, slow, _ok()])

    records = run_single_pass(
        provider,
        [campus],
        ["initial", "with_answers"],
        repeats=1,
        max_output_tokens=10,
        pacer=_pacer(Clock()),
        settings=NO_CHECKS,
    )

    assert [(r.mode, r.valid) for r in records] == [("initial", False), ("with_answers", True)]
    assert records[0].error == "timeout: slow"
    assert records[0].calls == 3


def test_call_cap_stops_before_overspending(campus: Pack) -> None:
    provider = FakeProvider([_ok(), _ok()])

    records = run_single_pass(
        provider,
        [campus],
        ["initial"],
        repeats=3,
        max_output_tokens=10,
        pacer=_pacer(Clock(), max_calls=4),
        settings=NO_CHECKS,
    )

    assert len(records) == 2
    assert len(provider.requests) == 2


def test_report_and_review_sheet_are_written(campus: Pack, tmp_path: Path) -> None:
    records = run_single_pass(
        FakeProvider([_ok()]),
        [campus],
        ["initial"],
        repeats=1,
        max_output_tokens=10,
        pacer=_pacer(Clock()),
        settings=NO_CHECKS,
    )

    json_path, sheet_path = write_report(
        records, model_id="gemini-3.5-flash-lite", split="dev", configuration={}, directory=tmp_path
    )

    assert json_path.name.endswith("-single-pass-gemini-3.5-flash-lite-dev.json")
    assert sheet_path.name.endswith("-gemini-3.5-flash-lite-dev.review.md")
    report = json.loads(json_path.read_text())
    assert report["prompt_version"][0].startswith("draft-v3+")
    assert report["schema_version"] == ["draft-backlog.v2"]
    assert report["summary"]["initial"]["runs"] == 1
    assert "| campus-room-booking | initial | 1 | CR-01 |" in sheet_path.read_text()
    assert "Human verdict" in review_sheet(records)


@pytest.mark.parametrize("command", ["single-pass", "agent", "change"])
def test_heldout_runs_require_the_final_flag(monkeypatch: pytest.MonkeyPatch, command: str) -> None:
    monkeypatch.setattr(sys, "argv", ["scopesteps-evals", command, "--split", "heldout"])

    with pytest.raises(SystemExit) as exited:
        cli.main()

    assert exited.value.code == 2


def test_validate_skips_heldout_when_not_cloned(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "heldout_present", lambda: False)
    monkeypatch.setattr(sys, "argv", ["scopesteps-evals", "validate"])

    with pytest.raises(SystemExit) as exited:
        cli.main()

    assert exited.value.code == 0
    out = capsys.readouterr().out
    assert "skip heldout" in out
    assert "LOCK" not in out


@pytest.mark.parametrize("command", ["single-pass", "agent", "change"])
def test_heldout_runs_need_the_packs_cloned(monkeypatch: pytest.MonkeyPatch, command: str) -> None:
    monkeypatch.setattr(cli, "heldout_present", lambda: False)
    monkeypatch.setattr(sys, "argv", ["scopesteps-evals", command, "--split", "heldout", "--final"])

    with pytest.raises(SystemExit) as exited:
        cli.main()

    assert exited.value.code == 2


def test_rescore_rebuilds_results_from_saved_drafts(campus: Pack, tmp_path: Path) -> None:
    records = run_single_pass(
        FakeProvider([_ok()]),
        [campus],
        ["initial"],
        repeats=1,
        max_output_tokens=10,
        pacer=_pacer(Clock()),
        settings=NO_CHECKS,
    )
    json_path, _ = write_report(
        records, model_id="m", split="dev", configuration={}, directory=tmp_path
    )
    report = json.loads(json_path.read_text())
    report["runs"][0]["results"] = []
    json_path.write_text(json.dumps(report))

    _, sheet_path = rescore_report(json_path, [campus])

    rescored = json.loads(json_path.read_text())
    assert len(rescored["runs"][0]["results"]) == len(records[0].results)
    assert "Draft text" in sheet_path.read_text()


@pytest.mark.parametrize(
    ("successes", "trials", "low", "high"),
    [(10, 10, 0.72, 1.0), (5, 6, 0.44, 0.97), (0, 0, 0.0, 1.0)],
)
def test_wilson_interval_reflects_small_samples(
    successes: int, trials: int, low: float, high: float
) -> None:
    lower, upper = wilson_interval(successes, trials)

    assert lower == pytest.approx(low, abs=0.01)
    assert upper == pytest.approx(high, abs=0.01)


def test_summary_reports_counts_intervals_and_traces_file(campus: Pack, tmp_path: Path) -> None:
    records = run_single_pass(
        FakeProvider([_ok()]),
        [campus],
        ["initial"],
        repeats=1,
        max_output_tokens=10,
        pacer=_pacer(Clock()),
        settings=NO_CHECKS,
    )

    row = summarize(records)["initial"]
    json_path, _ = write_report(
        records,
        model_id="m",
        split="dev",
        configuration={},
        directory=tmp_path,
        traces=[{"gen_ai.request.model": "m"}],
    )

    assert row["requirement_coverage_count"] == "0/7"
    assert row["requirement_coverage_ci95"] == "0%-35%"
    assert records[0].run_id
    traces = json_path.parent / json_path.name.replace(".json", ".traces.jsonl")
    assert json.loads(traces.read_text()) == {"gen_ai.request.model": "m"}


def test_a_request_too_large_fails_that_draft_only(campus: Pack) -> None:
    too_large = ModelProviderError("request_too_large", "too large")
    provider = FakeProvider([too_large, _ok()])

    records = run_single_pass(
        provider,
        [campus],
        ["initial", "with_answers"],
        repeats=1,
        max_output_tokens=10,
        pacer=_pacer(Clock()),
        settings=NO_CHECKS,
    )

    assert [(r.mode, r.valid, r.calls) for r in records] == [
        ("initial", False, 1),
        ("with_answers", True, 1),
    ]


def test_a_repair_too_large_after_an_unparsable_draft_keeps_its_calls_and_tokens(
    campus: Pack,
) -> None:
    """2026-10-15 Groq run: the first call completed but did not parse, and its repair was too
    large to send. The run used to be reported with 0 tokens and only the failed call."""
    too_large = ModelProviderError("request_too_large", "too large")
    provider = FakeProvider([_ok("{not json"), too_large])

    [record] = run_single_pass(
        provider,
        [campus],
        ["initial"],
        repeats=1,
        max_output_tokens=10,
        pacer=_pacer(Clock()),
        settings=NO_CHECKS,
    )

    assert not record.valid
    assert record.error is not None
    assert record.error.startswith("repair_too_large:")
    assert record.repair_error == "request_too_large: too large"
    assert (record.calls, record.total_tokens, record.latency_ms) == (2, 7, 100)
    assert record.repair == "full"
    assert record.draft is None


def test_a_repair_too_large_keeps_a_valid_draft_and_scores_it(campus: Pack) -> None:
    too_large = ModelProviderError("request_too_large", "too large")
    provider = FakeProvider([_ok(), too_large])

    [record] = run_single_pass(
        provider,
        [campus],
        ["initial"],
        repeats=1,
        max_output_tokens=10,
        pacer=_pacer(Clock()),
        settings=DraftSettings(prompt="draft-v3"),
    )

    assert record.valid
    assert record.repair_error == "request_too_large: too large"
    assert (record.calls, record.total_tokens) == (2, 7)
    assert record.draft is not None
    assert record.results


def test_console_line_names_a_failure_reason_only_when_there_is_one(campus: Pack) -> None:
    from scopesteps.evals.runner import RunRecord

    valid = RunRecord(campus.id, "initial", 1, True, None, 1, False, 0, 0)
    assert cli.run_line(valid) == "ok"
    valid.results = [{"annotation_id": "CR-01", "verdict": "fail"}]
    assert cli.run_line(valid) == "ok; failed CR-01"
    invalid = RunRecord(campus.id, "initial", 1, False, "repair_too_large: x", 2, False, 0, 0)
    assert cli.run_line(invalid) == "invalid (repair_too_large: x)"
