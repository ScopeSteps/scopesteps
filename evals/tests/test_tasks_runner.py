import json
from pathlib import Path
from typing import Any

from scopesteps.agent.client import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    RunLimits,
    Usage,
)
from scopesteps.evals.packs import DATASETS_DIR, load_pack
from scopesteps.evals.runner import Pacer
from scopesteps.evals.tasks_runner import (
    reference_outline,
    run_tasks,
    summarize_tasks,
    write_tasks_report,
)

CAMPUS = load_pack(DATASETS_DIR / "dev" / "campus-room-booking", "dev")
LIMITS = RunLimits(
    max_turns=20, max_tool_calls=8, max_output_tokens_per_call=8000, max_total_tokens=400_000
)


class Scripted:
    """Answers every request with tasks for each story it was sent: one taken from the story's
    title, which the scope check passes, and one about payments, which it flags."""

    def __init__(self, fail_first: bool = False) -> None:
        self.requests: list[ModelRequest] = []
        self.fail_first = fail_first

    def generate(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        if self.fail_first and len(self.requests) == 1:
            raise ModelProviderError("unavailable", "busy", status_code=503)
        assert request.output_schema is not None
        stories = [
            {"story": label, "tasks": ["Build the part this story names", "Set up card payments"]}
            for label in _labels(dict(request.output_schema))
        ]
        text = json.dumps({"stories": stories})
        return ModelResult(
            "test",
            "gemini-3.5-flash-lite",
            ModelTurn(({"type": "model_output", "text": text},)),
            text,
            (),
            "completed",
            Usage(input_tokens=700, output_tokens=90, total_tokens=790),
            30,
        )


def _labels(schema: dict[str, Any]) -> list[str]:
    """The story labels a request offers: the enum on each answer's `story`."""
    stories = schema["properties"]["stories"]["items"]
    if "$ref" in stories:
        stories = schema["$defs"][stories["$ref"].rsplit("/", 1)[-1]]
    return [str(label) for label in stories["properties"]["story"]["enum"]]


def _pacer() -> Pacer:
    return Pacer(requests_per_minute=600, max_calls=100, sleep=lambda _: None, log=lambda _: None)


def test_the_reference_backlog_has_one_story_per_confirmed_requirement() -> None:
    outline = reference_outline(CAMPUS)

    confirmed = [a for a in CAMPUS.annotations.annotations if a.kind == "confirmed_requirement"]
    left_out = [a for a in CAMPUS.annotations.annotations if a.kind in {"exclusion", "proposal"}]
    assert len(outline.items) == len(confirmed)
    assert {item.kind for item in outline.items} == {"story"}
    assert len(outline.out_of_scope) == len(left_out)


def test_every_story_gets_suggestions_and_flagged_tasks_are_counted_out_of_scope() -> None:
    provider = Scripted()

    (record,) = run_tasks(
        provider,
        [CAMPUS],
        repeats=1,
        provider_name="gemini",
        model_id="gemini-3.5-flash-lite",
        limits=LIMITS,
        pacer=_pacer(),
        prompt="tasks-v1",
    )

    assert record.status == "completed"
    assert record.stories_answered == record.stories
    assert len(record.tasks) == 2 * record.stories
    payments = [t for t in record.tasks if t.task == "Set up card payments"]
    assert all(t.problem is not None for t in payments)
    summary = summarize_tasks([record])
    assert summary["tasks"] == 2 * record.stories
    assert summary["tasks_in_scope"] == record.in_scope
    assert summary["in_scope_share"] is not None
    assert summary["in_scope_share"] <= 0.5
    assert len(provider.requests) == record.calls


def test_a_run_stopped_by_the_provider_is_reported_with_its_error() -> None:
    (record,) = run_tasks(
        Scripted(fail_first=True),
        [CAMPUS],
        repeats=1,
        provider_name="gemini",
        model_id="gemini-3.5-flash-lite",
        limits=LIMITS,
        pacer=_pacer(),
        prompt="tasks-v1",
    )

    assert (record.status, record.error) == ("running", "MODEL_UNAVAILABLE")
    assert record.tasks == []


def test_the_report_lists_only_flagged_tasks_for_a_person_to_read(tmp_path: Path) -> None:
    records = run_tasks(
        Scripted(),
        [CAMPUS],
        repeats=1,
        provider_name="gemini",
        model_id="gemini-3.5-flash-lite",
        limits=LIMITS,
        pacer=_pacer(),
        prompt="tasks-v1",
    )

    json_path, sheet_path = write_tasks_report(
        records, model_id="m", prompt="tasks-v1", configuration={}, reports_dir=tmp_path
    )

    report = json.loads(json_path.read_text())
    rows = sheet_path.read_text().splitlines()[1:]
    assert report["summary"]["tasks"] == len(records[0].tasks)
    assert len(rows) == len(records[0].tasks) - records[0].in_scope
    assert all("Set up card payments" in row for row in rows if "payments" in row)
