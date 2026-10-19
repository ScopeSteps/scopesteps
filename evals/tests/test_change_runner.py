"""Change analysis on the packs' change requests with a scripted model: no live calls."""

import json
from pathlib import Path

from scopesteps.agent.client import (
    ModelRequest,
    ModelResult,
    ModelTurn,
    RunLimits,
    SpeakerNote,
    Usage,
    UserMessage,
)
from scopesteps.evals.change_runner import (
    block_labels,
    reference_baseline,
    run_changes,
    summarize_changes,
    write_change_report,
)
from scopesteps.evals.packs import CHANGE_REQUEST_FILE, DATASETS_DIR, load_pack
from scopesteps.evals.runner import Pacer

CAMPUS = load_pack(DATASETS_DIR / "dev" / "campus-room-booking", "dev")
LIMITS = RunLimits(
    max_turns=6, max_tool_calls=8, max_output_tokens_per_call=8000, max_total_tokens=200_000
)


class Scripted:
    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        text = self.texts.pop(0)
        return ModelResult(
            "test",
            "gemini-3.5-flash-lite",
            ModelTurn(({"type": "model_output", "text": text},)),
            text,
            (),
            "completed",
            Usage(input_tokens=900, output_tokens=60, total_tokens=960),
            40,
        )


NO_CHANGE = json.dumps(
    {
        "outcome": "no_change_needed",
        "summary": "The baseline already covers the request.",
        "summary_citations": [],
        "covered_by": ["S1"],
        "operations": [],
        "scope_decisions": [],
        "questions": [],
        "impacts": [],
    }
)


def test_the_reference_baseline_is_built_from_the_answer_key() -> None:
    baseline = reference_baseline(CAMPUS)
    confirmed = [a for a in CAMPUS.annotations.annotations if a.kind == "confirmed_requirement"]
    excluded = [a for a in CAMPUS.annotations.annotations if a.kind == "exclusion"]

    assert set(baseline.stories) == {a.id for a in confirmed}
    assert set(baseline.exclusions) == {a.id for a in excluded}
    assert baseline.version.state == "approved"
    request_labels = [k for k in block_labels(baseline) if k[0] == CHANGE_REQUEST_FILE]
    assert len(request_labels) == len(CAMPUS.blocks[CHANGE_REQUEST_FILE])
    assert baseline.passages[-1].source_kind == "change_request", "the request is pinned last"


def test_a_run_that_changes_nothing_fails_every_impact_that_needs_work(tmp_path: Path) -> None:
    provider = Scripted(["READY", NO_CHANGE])

    records = run_changes(
        provider,
        [CAMPUS],
        repeats=1,
        provider_name="test",
        model_id="gemini-3.5-flash-lite",
        limits=LIMITS,
        max_clarification_rounds=1,
        pacer=Pacer(requests_per_minute=10_000, max_calls=10),
    )

    (record,) = records
    assert (record.valid, record.outcome, record.unintended_edits) == (
        True,
        "no_change_needed",
        0,
    )
    verdicts = {v["expect"]: v["verdict"] for v in record.results}
    assert verdicts["add"] == "fail"
    assert "pass" not in {v["verdict"] for v in record.results if v["expect"] != "unchanged"}
    summary = summarize_changes(records)
    assert (summary["runs"], summary["valid"]) == (1, 1)
    json_path, sheet_path = write_change_report(
        records, model_id="test", split="dev", configuration={}, directory=tmp_path
    )
    assert json.loads(json_path.read_text())["summary"]["runs"] == 1
    assert sheet_path.read_text().startswith("# Change analysis review sheet")


def test_the_reference_baseline_pins_the_pack_s_confirmed_speakers() -> None:
    baseline = reference_baseline(CAMPUS)

    spoken = {(p.source_kind, p.ordinal): p.speakers for p in baseline.passages if p.speakers}

    assert spoken == CAMPUS.notes
    assert SpeakerNote("Dana", "Dana Ruiz", "Sponsor") in {n for s in spoken.values() for n in s}


def test_change_v2_runs_show_the_pack_s_confirmed_speakers(tmp_path: Path) -> None:
    provider = Scripted(["READY", NO_CHANGE])

    (record,) = run_changes(
        provider,
        [CAMPUS],
        repeats=1,
        provider_name="test",
        model_id="gemini-3.5-flash-lite",
        limits=LIMITS,
        max_clarification_rounds=1,
        pacer=Pacer(requests_per_minute=10_000, max_calls=10),
        prompt="change-v2",
    )

    assert record.prompt_version.startswith("change-explore-v2+")
    for request in provider.requests:
        first = request.history[0]
        assert isinstance(first, UserMessage)
        assert 'speakers="Dana: Dana Ruiz, Sponsor"' in first.text
    json_path, _ = write_change_report(
        [record],
        model_id="test",
        split="dev",
        configuration={},
        directory=tmp_path,
        prompt="change-v2",
    )
    assert json.loads(json_path.read_text())["prompt_version"] == record.prompt_version
    assert "-change-v2-" in json_path.name
