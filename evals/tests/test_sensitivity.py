import json
from pathlib import Path

import pytest

from scopesteps.agent.client import (
    DRAFT_PROMPTS,
    ModelRequest,
    ModelResult,
    ModelTurn,
    Usage,
)
from scopesteps.evals.packs import DATASETS_DIR, Pack, load_pack
from scopesteps.evals.runner import Pacer, RunRecord
from scopesteps.evals.sensitivity import (
    ORIGINAL,
    RewordedProvider,
    Variant,
    changed_annotations,
    compare,
    load_variants,
    run_sensitivity,
    validate_variants,
    variant_problems,
    write_sensitivity_report,
)

EMPTY_DRAFT = json.dumps({"statements": [], "items": [], "questions": [], "people": []})


class RecordingProvider:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        return ModelResult(
            "test", "m", ModelTurn(()), EMPTY_DRAFT, (), "completed", Usage(total_tokens=7), 100
        )


def _pacer() -> Pacer:
    return Pacer(
        10_000, 100, sleep=lambda _: None, clock=lambda: 0.0, log=lambda _: None, jitter=lambda: 0.0
    )


@pytest.fixture(scope="module")
def campus() -> Pack:
    return load_pack(DATASETS_DIR / "dev" / "campus-room-booking", "dev")


def _record(verdict: str, repeat: int) -> RunRecord:
    return RunRecord(
        pack="p",
        mode="initial",
        repeat=repeat,
        valid=True,
        error=None,
        calls=1,
        repaired=False,
        latency_ms=1,
        total_tokens=1,
        results=[{"annotation_id": "CR-01", "kind": "confirmed_requirement", "verdict": verdict}],
    )


def test_every_reworded_prompt_on_disk_keeps_the_original_terms() -> None:
    found = validate_variants()

    assert {"draft-v10/plain", "draft-v10/terse", "draft-v10/reordered"} <= set(found)
    assert {name: problems for name, problems in found.items() if problems} == {}


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (('origin "proposed"', "origin proposed"), 'missing quoted term "proposed"'),
        (("At most 2 epics", "At most 3 epics"), "missing id or number 2"),
        (("<source> tags", "source tags"), "missing tag <source>"),
        (("cite every source block", "cite every source block"), "identical to the original"),
    ],
)
def test_a_rewording_that_changes_what_is_asked_is_refused(
    change: tuple[str, str], problem: str
) -> None:
    original = DRAFT_PROMPTS["draft-v10"]
    old, new = change

    problems = variant_problems(original, original.replace(old, new))

    assert problem in problems


def test_variants_take_turns_and_each_sends_its_own_wording(campus: Pack) -> None:
    provider = RecordingProvider()
    variants = [load_variants("draft-v10")[0], Variant("short", "Reworded prompt.\n")]

    results = run_sensitivity(
        provider,
        [campus],
        ["initial"],
        variants,
        prompt="draft-v10",
        repeats=2,
        max_output_tokens=10,
        pacer=_pacer(),
    )

    assert [(name, record.repeat) for name, record in results] == [
        (ORIGINAL, 1),
        ("short", 1),
        (ORIGINAL, 2),
        ("short", 2),
    ]
    assert {request.system_instruction for request in provider.requests} == {
        DRAFT_PROMPTS["draft-v10"],
        "Reworded prompt.\n",
    }
    assert results[1][1].prompt_version == f"draft-v10+{variants[1].version}"
    assert results[0][1].prompt_version != results[1][1].prompt_version


def test_reworded_provider_refuses_a_call_with_another_prompt() -> None:
    provider = RewordedProvider(RecordingProvider(), original="A", reworded="B")
    request = ModelRequest(system_instruction="C", history=(), max_output_tokens=10)

    with pytest.raises(ValueError, match="did not use the prompt"):
        provider.generate(request)


def test_comparison_proves_only_a_difference_whose_intervals_do_not_overlap() -> None:
    results = (
        [(ORIGINAL, _record("pass", n)) for n in range(1, 11)]
        + [("same", _record("pass" if n < 10 else "fail", n)) for n in range(1, 11)]
        + [("worse", _record("fail", n)) for n in range(1, 11)]
    )

    rows = {row["metric"]: row for row in compare(results)["initial"]}

    coverage = rows["requirement_coverage"]
    assert coverage["values"][ORIGINAL] == "10/10 (72%-100%)"
    assert coverage["spread_points"] == 100
    assert coverage["verdict"] == "differs: worse"
    assert rows["valid_drafts"]["verdict"] == "no proven difference"
    assert changed_annotations(results) == {
        "p:CR-01": {"initial": {ORIGINAL: "10/10", "same": "9/10", "worse": "0/10"}}
    }


def test_report_and_readable_summary_are_written(tmp_path: Path) -> None:
    results = [(ORIGINAL, _record("pass", 1)), ("terse", _record("fail", 1))]

    json_path, sheet_path = write_sensitivity_report(
        results,
        prompt="draft-v10",
        variants=[Variant(ORIGINAL, "a"), Variant("terse", "b")],
        model_id="m",
        configuration={"packs": ["p"], "repeats": 1},
        directory=tmp_path,
    )

    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert [run["variant"] for run in report["runs"]] == [ORIGINAL, "terse"]
    sheet = sheet_path.read_text(encoding="utf-8")
    assert "| Metric | original | terse | Spread | Verdict |" in sheet
    assert "`p:CR-01` (initial): original 1/1, terse 0/1" in sheet
