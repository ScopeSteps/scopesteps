"""Score the tasks the agent suggests (`tasks-v1`) by whether they stay inside their story.

Each pack's reference backlog is built from its annotations: one story per confirmed
requirement, the exclusions and proposals as out of scope. The agent suggests tasks for every
story with the steps a task-suggestion run takes (`suggest_tasks_offline`), and each task is
scored with the same code check the API shows on every task (`task_scope_problem`):

- in scope: the check finds nothing.
- out of scope: the check names excluded work or something no story of the backlog mentions. A
  person reads these in the sheet: the check is deliberately simple and can flag a fair task.

The headline is the share of suggested tasks in scope, with its 95% Wilson interval. Tasks are
not in the packs' gold data, so there is no recall to report.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from scopesteps.agent.client import (
    ModelProvider,
    RunLimits,
    RunStatus,
    suggest_tasks_offline,
    trace_scope,
)
from scopesteps.backlog.client import (
    BacklogOutline,
    BacklogVersionId,
    ItemId,
    OutlineItem,
    VersionState,
    task_scope_problem,
)
from scopesteps.evals.packs import Pack
from scopesteps.evals.runner import REPORTS_DIR, Pacer, RunStoppedError, wilson_interval


@dataclass
class TaskVerdict:
    story: str
    task: str
    problem: str | None


@dataclass
class TasksRecord:
    pack: str
    repeat: int
    status: str
    error: str | None
    calls: int
    total_tokens: int
    stories: int
    stories_answered: int
    tasks: list[TaskVerdict] = field(default_factory=list[TaskVerdict])
    restated: int = 0
    """Stories whose only suggested task said the story again, left without tasks by code."""

    @property
    def in_scope(self) -> int:
        return sum(1 for task in self.tasks if task.problem is None)


def reference_outline(pack: Pack) -> BacklogOutline:
    """The pack's confirmed requirements as stories of one epic, and what it leaves out."""
    epic = pack.annotations.pack.title
    stories = tuple(
        OutlineItem(
            kind="story",
            title=annotation.statement[:200],
            description=annotation.statement,
            criteria=(annotation.statement,),
            parent_title=epic,
            id=ItemId(uuid4()),
        )
        for annotation in pack.annotations.annotations
        if annotation.kind == "confirmed_requirement"
    )
    left_out = tuple(
        annotation.statement
        for annotation in pack.annotations.annotations
        if annotation.kind in {"exclusion", "proposal"}
    )
    return BacklogOutline(
        version_id=BacklogVersionId(uuid4()),
        state=VersionState.DRAFT,
        items=stories,
        open_decisions=(),
        out_of_scope=left_out,
    )


def score_tasks(
    outline: BacklogOutline, suggested: dict[ItemId, tuple[str, ...]]
) -> list[TaskVerdict]:
    stories = {item.id: item for item in outline.items if item.id is not None}
    return [
        TaskVerdict(
            story.title, title, task_scope_problem(title, outline.items, outline.out_of_scope)
        )
        for story_id, titles in suggested.items()
        if (story := stories.get(story_id)) is not None
        for title in titles
    ]


def run_tasks(
    provider: ModelProvider,
    packs: Sequence[Pack],
    *,
    repeats: int,
    provider_name: str,
    model_id: str,
    limits: RunLimits,
    pacer: Pacer,
    prompt: str,
) -> list[TasksRecord]:
    records: list[TasksRecord] = []
    try:
        for repeat in range(1, repeats + 1):
            for pack in packs:
                outline = reference_outline(pack)
                with trace_scope(pack=pack.id, repeat=repeat):
                    result = suggest_tasks_offline(
                        provider,
                        outline,
                        provider_name=provider_name,
                        model_id=model_id,
                        limits=limits,
                        prompt=prompt,
                        before_step=lambda: pacer.reserve(1),
                    )
                run = result.run
                records.append(
                    TasksRecord(
                        pack=pack.id,
                        repeat=repeat,
                        status=run.status.value,
                        error=None if run.error is None else run.error.code,
                        calls=run.counters.model_turns,
                        total_tokens=run.counters.total_tokens,
                        stories=sum(1 for item in outline.items if item.kind == "story"),
                        stories_answered=len(result.suggested),
                        tasks=score_tasks(outline, dict(result.suggested)),
                        restated=sum(
                            int(str(step.detail.get("restated", 0)))
                            for step in result.steps
                            if step.name == "validate_tasks"
                        ),
                    )
                )
                if run.status != RunStatus.COMPLETED:
                    pacer.log(
                        f"{pack.id} repeat {repeat}: {run.status.value} ({records[-1].error})"
                    )
    except RunStoppedError as stop:
        pacer.log(f"Stopped early: {stop}. Partial results are kept.")
    return records


def rescore_records(report: dict[str, Any], packs: Sequence[Pack]) -> list[TasksRecord]:
    """A saved report's tasks scored again with the current check, without model calls. Each
    task is checked against its pack's reference backlog, which is rebuilt from the pack."""
    outlines = {pack.id: reference_outline(pack) for pack in packs}
    records: list[TasksRecord] = []
    for saved in report["records"]:
        outline = outlines[saved["pack"]]
        tasks = [
            TaskVerdict(
                task["story"],
                task["task"],
                task_scope_problem(task["task"], outline.items, outline.out_of_scope),
            )
            for task in saved["tasks"]
        ]
        records.append(
            TasksRecord(
                pack=str(saved["pack"]),
                repeat=int(saved["repeat"]),
                status=str(saved["status"]),
                error=None if saved["error"] is None else str(saved["error"]),
                calls=int(saved["calls"]),
                total_tokens=int(saved["total_tokens"]),
                stories=int(saved["stories"]),
                stories_answered=int(saved["stories_answered"]),
                tasks=tasks,
                restated=int(saved.get("restated", 0)),
            )
        )
    return records


def summarize_tasks(records: Sequence[TasksRecord]) -> dict[str, Any]:
    tasks = sum(len(record.tasks) for record in records)
    in_scope = sum(record.in_scope for record in records)
    low, high = wilson_interval(in_scope, tasks)
    stories = sum(record.stories for record in records)
    return {
        "runs": len(records),
        "runs_completed": sum(1 for record in records if record.status == "completed"),
        "tasks": tasks,
        "tasks_in_scope": in_scope,
        "in_scope_share": round(in_scope / tasks, 3) if tasks else None,
        "in_scope_interval": [round(low, 3), round(high, 3)],
        "tasks_per_story": round(tasks / stories, 2) if stories else None,
        "stories_with_tasks": sum(len({t.story for t in record.tasks}) for record in records),
        "stories_left_one_step": sum(record.restated for record in records),
        "stories_answered_share": round(
            sum(record.stories_answered for record in records) / stories, 3
        )
        if stories
        else None,
        "calls": sum(record.calls for record in records),
    }


def write_tasks_report(
    records: Sequence[TasksRecord],
    *,
    model_id: str,
    prompt: str,
    configuration: dict[str, Any],
    reports_dir: Path = REPORTS_DIR,
) -> tuple[Path, Path]:
    """A JSON report and a sheet listing each flagged task for a person to read."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    reports_dir.mkdir(parents=True, exist_ok=True)
    # Model ids hold dots ("gemini-3.5-flash-lite"), so names are joined by hand, not
    # `with_suffix`, which would cut the name at the last dot.
    stem = f"tasks-{prompt}-{model_id}-{stamp}"
    report = {
        "prompt": prompt,
        "model_id": model_id,
        "configuration": configuration,
        "summary": summarize_tasks(records),
        "records": [asdict(record) for record in records],
    }
    json_path = reports_dir / f"{stem}.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    lines = ["pack\trepeat\tstory\ttask\tproblem"]
    lines += [
        f"{record.pack}\t{record.repeat}\t{task.story}\t{task.task}\t{task.problem}"
        for record in records
        for task in record.tasks
        if task.problem is not None
    ]
    sheet_path = reports_dir / f"{stem}.tsv"
    sheet_path.write_text("\n".join(lines) + "\n")
    return json_path, sheet_path
