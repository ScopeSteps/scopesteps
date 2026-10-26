import json
from dataclasses import replace
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
    by_pack,
    changed_annotations,
    compare,
    load_variants,
    paired_difference,
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


def _record(verdicts: str, repeat: int) -> RunRecord:
    """A valid draft whose requirements CR-01, CR-02, ... got these verdicts ('p' passes)."""
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
        results=[
            {
                "annotation_id": f"CR-{n:02}",
                "kind": "confirmed_requirement",
                "verdict": "pass" if verdict == "p" else "fail",
            }
            for n, verdict in enumerate(verdicts, start=1)
        ],
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


def test_a_change_is_proven_only_when_its_paired_interval_excludes_zero() -> None:
    # Ten requirements over five repeats: "noisy" loses one pass on one requirement, "worse"
    # fails half of every requirement's repeats.
    results = (
        [(ORIGINAL, _record("pppppppppp", n)) for n in range(1, 6)]
        + [("noisy", _record("fppppppppp" if n == 1 else "pppppppppp", n)) for n in range(1, 6)]
        + [("worse", _record("ffffffffff" if n % 2 else "pppppppppp", n)) for n in range(1, 6)]
    )

    rows = {row["metric"]: row for row in compare(results)["initial"]}

    coverage = rows["requirement_coverage"]
    assert coverage["values"][ORIGINAL] == "50/50 (93%-100%)"
    assert coverage["change_from_original"]["worse"] == "-60.0 pts (-60.0 to -60.0)"
    assert coverage["change_from_original"]["noisy"].startswith("-2.0 pts (-6.0 to +0.0)")
    assert coverage["verdict"] == "worse: worse"
    assert rows["valid_drafts"]["verdict"] is None
    assert changed_annotations(results)["p:CR-01"] == {
        "initial": {ORIGINAL: "5/5", "noisy": "4/5", "worse": "2/5"}
    }


def test_paired_difference_is_none_without_shared_annotations() -> None:
    assert paired_difference([_record("p", 1)], [], "initial", {"confirmed_requirement"}) is None


def test_report_and_readable_summary_are_written(tmp_path: Path) -> None:
    results = [(ORIGINAL, _record("p", 1)), ("terse", _record("f", 1))]

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
    assert "| Metric | original | terse | Spread |" in sheet
    assert "| Metric | terse | Verdict |" in sheet
    assert "`p:CR-01` (initial): original 1/1, terse 0/1" in sheet


def test_results_by_pack_list_the_easiest_and_shortest_packs_first() -> None:
    hard = load_pack(DATASETS_DIR / "dev" / "youth-football-registration", "dev")
    easy = load_pack(DATASETS_DIR / "dev" / "clinic-appointment-reminders", "dev")
    record = replace(_record("pf", 1), pack=easy.id)

    rows = by_pack([(ORIGINAL, record)], [hard, easy])["initial"]

    assert [(row["pack"], row["difficulty"]) for row in rows] == [
        (easy.id, "easy"),
        (hard.id, "hard"),
    ]
    assert rows[0]["values"] == {ORIGINAL: "1/2 (50%)"}
    assert rows[1]["values"] == {}
    assert rows[0]["words"] < rows[1]["words"]


def test_an_invalid_draft_does_not_mark_every_annotation_as_changed() -> None:
    invalid = replace(_record("", 2), valid=False)
    results = [
        (ORIGINAL, _record("pp", 1)),
        (ORIGINAL, invalid),
        ("terse", _record("pp", 1)),
        ("terse", _record("pf", 2)),
    ]

    assert changed_annotations(results) == {
        "p:CR-02": {"initial": {ORIGINAL: "1/1", "terse": "1/2"}}
    }
