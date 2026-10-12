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
    Pacer,
    annotation_stability,
    review_sheet,
    run_single_pass,
    summarize,
    write_report,
)

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
    return Pacer(15, max_calls, sleep=clock.sleep, clock=clock, log=lambda _: None)


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
        provider, [campus], ["initial"], repeats=1, max_output_tokens=10, pacer=_pacer(clock)
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
    )

    assert [r.mode for r in records] == ["initial"]


def test_transient_errors_are_recorded_and_the_run_continues(campus: Pack) -> None:
    provider = FakeProvider([ModelProviderError("timeout", "slow"), _ok()])

    records = run_single_pass(
        provider,
        [campus],
        ["initial", "with_answers"],
        repeats=1,
        max_output_tokens=10,
        pacer=_pacer(Clock()),
    )

    assert [(r.mode, r.valid) for r in records] == [("initial", False), ("with_answers", True)]
    assert records[0].error == "timeout: slow"


def test_call_cap_stops_before_overspending(campus: Pack) -> None:
    provider = FakeProvider([_ok(), _ok()])

    records = run_single_pass(
        provider,
        [campus],
        ["initial"],
        repeats=3,
        max_output_tokens=10,
        pacer=_pacer(Clock(), max_calls=4),
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
    )

    json_path, sheet_path = write_report(
        records, model_id="gemini-3.5-flash-lite", split="dev", configuration={}, directory=tmp_path
    )

    assert json_path.name.endswith("-single-pass-gemini-3.5-flash-lite-dev.json")
    assert sheet_path.name.endswith("-gemini-3.5-flash-lite-dev.review.md")
    report = json.loads(json_path.read_text())
    assert report["prompt_version"].startswith("draft-v1+")
    assert report["summary"]["initial"]["runs"] == 1
    assert "| campus-room-booking | initial | 1 | CR-01 |" in sheet_path.read_text()
    assert "Human verdict" in review_sheet(records)


def test_heldout_runs_require_the_final_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["scopesteps-evals", "single-pass", "--split", "heldout"])

    with pytest.raises(SystemExit) as exited:
        cli.main()

    assert exited.value.code == 2
