"""How consistent the agent is across repeats of the same input, from a saved report's runs.

Averages hide a requirement found in one run and missed in the next. These scores show it:

- **Found in every, some or no repeats:** per pack, the share of expected requirements a draft
  found in every repeat, in some or in none. A repeat with no valid draft found nothing.
- **Pass in every repeat:** per metric, the share of scored items (annotations, change impacts,
  reply questions) that pass in all repeats, beside the mean pass rate, per mode (or variant and
  mode) and, except in a sensitivity report, across all of them. It is the stricter
  "pass^k" reading: an item that passes two runs in three counts as not passing.
- **Spread between repeats:** per pack, the lowest and highest story count and number of
  problems left after repair, over the repeats with a valid draft.

Everything is computed from what a report already holds, so past reports get the scores with
`scopesteps-evals consistency` and no model call. Verdicts still `needs_review` are left out.
"""

import json
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

REQUIREMENT_KIND = "confirmed_requirement"
# The metric groups a draft's annotations are scored in (runner.KIND_GROUPS), by kind.
_METRIC_BY_KIND = {
    "confirmed_requirement": "requirement_coverage",
    "exclusion": "exclusions_and_proposals_respected",
    "proposal": "exclusions_and_proposals_respected",
    "conflict": "conflicts_and_gaps_handled",
    "missing_decision": "conflicts_and_gaps_handled",
    "injection": "injection_ignored",
}
CHANGE_METRIC = "change_impacts"
REPLY_METRIC = "reply_answers"

Json = dict[str, Any]


@dataclass(frozen=True)
class Observation:
    """One scored item in one repeat: `group` is the input it belongs to (pack, mode)."""

    group: str
    metric: str
    item: str
    repeat: int
    passed: bool


@dataclass(frozen=True)
class Repeat:
    """One repeat of one input: whether it produced valid output and what it held."""

    group: str
    repeat: int
    valid: bool
    stories: int | None
    problems: int | None


@dataclass(frozen=True)
class Range:
    low: int
    high: int

    @property
    def spread(self) -> int:
        return self.high - self.low


@dataclass(frozen=True)
class Requirements:
    expected: int
    every: int
    some: int
    none: int

    def share(self, count: int) -> float | None:
        return count / self.expected if self.expected else None


@dataclass(frozen=True)
class GroupConsistency:
    group: str
    repeats: int
    valid_repeats: int
    requirements: Requirements | None
    stories: Range | None
    problems: Range | None


@dataclass(frozen=True)
class MetricConsistency:
    scope: str
    """The mode or variant the items were scored in, or `all`."""
    metric: str
    items: int
    pass_every: int
    mean_pass_rate: float

    @property
    def pass_every_rate(self) -> float:
        return self.pass_every / self.items


@dataclass(frozen=True)
class Consistency:
    groups: list[GroupConsistency] = field(default_factory=list[GroupConsistency])
    metrics: list[MetricConsistency] = field(default_factory=list[MetricConsistency])

    def as_json(self) -> Json:
        return {
            "groups": [
                asdict(group)
                | {
                    "requirements": None
                    if group.requirements is None
                    else asdict(group.requirements)
                    | {
                        "every_share": group.requirements.share(group.requirements.every),
                        "some_share": group.requirements.share(group.requirements.some),
                        "none_share": group.requirements.share(group.requirements.none),
                    },
                    "stories": _range_json(group.stories),
                    "problems": _range_json(group.problems),
                }
                for group in self.groups
            ],
            "metrics": [
                asdict(metric) | {"pass_every_rate": metric.pass_every_rate}
                for metric in self.metrics
            ],
        }


def _range_json(value: Range | None) -> Json | None:
    return None if value is None else asdict(value) | {"spread": value.spread}


def consistency(report: Json) -> Consistency:
    """The consistency scores of a saved report of any kind (draft, agent, sensitivity, change
    or reply)."""
    observations, repeats, items = _read(report)
    return Consistency(
        groups=[_group(name, observations, repeats, items) for name in _groups(repeats)],
        metrics=_metrics(observations, repeats, items),
    )


def add_consistency(path: Path) -> Consistency:
    """Write the scores into the report at `path`, replacing any earlier ones. No model call."""
    report = cast(Json, json.loads(path.read_text(encoding="utf-8")))
    scores = consistency(report)
    report["consistency"] = scores.as_json()
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return scores


def _read(
    report: Json,
) -> tuple[list[Observation], list[Repeat], dict[str, dict[str, set[str]]]]:
    """The report's verdicts and repeats, and every item each group was scored on.

    An item scored in any repeat is expected in all of them, so a repeat that produced no valid
    output counts as missing it.
    """
    observations: list[Observation] = []
    repeats: list[Repeat] = []
    items: dict[str, dict[str, set[str]]] = {}

    def observe(group: str, metric: str, item: str, repeat: int, verdict: str) -> None:
        items.setdefault(group, {}).setdefault(metric, set()).add(item)
        if verdict != "needs_review":
            observations.append(Observation(group, metric, item, repeat, verdict == "pass"))

    if "replies" in report:
        for reply in cast(list[Json], report["replies"]):
            group, repeat = str(reply["pack"]), int(reply["repeat"])
            repeats.append(Repeat(group, repeat, bool(reply["valid"]), None, None))
            observe(group, REPLY_METRIC, str(reply["question_id"]), repeat, str(reply["verdict"]))
        return observations, repeats, items

    for run in cast(list[Json], report["runs"]):
        group = _group_name(run)
        repeat, valid = int(run["repeat"]), bool(run["valid"])
        is_change = "change_set" in run or "outcome" in run
        draft = cast(Json | None, run.get("draft"))
        stories = (
            sum(1 for item in cast(list[Json], draft["items"]) if item.get("kind") == "story")
            if valid and draft is not None
            else None
        )
        problems_field = "problems" if is_change else "check_problems"
        problems = len(cast(list[str], run.get(problems_field, []))) if valid else None
        repeats.append(Repeat(group, repeat, valid, stories, problems))
        for result in cast(list[Json], run.get("results", [])):
            metric = CHANGE_METRIC if is_change else _METRIC_BY_KIND.get(str(result.get("kind")))
            if metric is not None:
                observe(group, metric, str(result["annotation_id"]), repeat, str(result["verdict"]))
    return observations, repeats, items


def _group_name(run: Json) -> str:
    parts = [str(run[key]) for key in ("variant", "pack", "mode") if run.get(key)]
    return " · ".join(parts)


def _groups(repeats: Iterable[Repeat]) -> list[str]:
    return sorted({repeat.group for repeat in repeats})


def _group(
    name: str,
    observations: Sequence[Observation],
    repeats: Sequence[Repeat],
    items: dict[str, dict[str, set[str]]],
) -> GroupConsistency:
    runs = [repeat for repeat in repeats if repeat.group == name]
    valid = [repeat for repeat in runs if repeat.valid]
    numbers = sorted({repeat.repeat for repeat in runs})
    # A reply report holds one entry per question and repeat: a repeat is valid when all are.
    valid_numbers = [n for n in numbers if all(r.valid for r in runs if r.repeat == n)]
    requirement_ids = items.get(name, {}).get("requirement_coverage", set())
    requirements = None
    if requirement_ids:
        found = {
            item: {
                o.repeat
                for o in observations
                if o.group == name
                and o.metric == "requirement_coverage"
                and o.item == item
                and o.passed
            }
            for item in requirement_ids
        }
        every = sum(len(repeats_found) == len(numbers) for repeats_found in found.values())
        none = sum(not repeats_found for repeats_found in found.values())
        requirements = Requirements(
            expected=len(requirement_ids),
            every=every,
            some=len(requirement_ids) - every - none,
            none=none,
        )
    return GroupConsistency(
        group=name,
        repeats=len(numbers),
        valid_repeats=len(valid_numbers),
        requirements=requirements,
        stories=_range(repeat.stories for repeat in valid),
        problems=_range(repeat.problems for repeat in valid),
    )


def _range(values: Iterable[int | None]) -> Range | None:
    present = [value for value in values if value is not None]
    return Range(min(present), max(present)) if present else None


def _metrics(
    observations: Sequence[Observation],
    repeats: Sequence[Repeat],
    items: dict[str, dict[str, set[str]]],
) -> list[MetricConsistency]:
    """Per scope (the group without its pack) and metric, then across every scope."""
    repeats_of: dict[str, set[int]] = {}
    for run in repeats:
        repeats_of.setdefault(run.group, set()).add(run.repeat)
    rows: dict[tuple[str, str], tuple[int, int, list[float]]] = {}
    for group, metrics in items.items():
        expected_repeats = repeats_of.get(group, set())
        for metric, ids in metrics.items():
            for item in ids:
                passes = [
                    o.passed
                    for o in observations
                    if o.group == group and o.metric == metric and o.item == item
                ]
                if not expected_repeats:
                    continue
                # A repeat that scored nothing for this item (no valid draft) is a miss.
                passed = sum(passes)
                every = passed == len(expected_repeats) and len(passes) == len(expected_repeats)
                # Pooling the variants of a sensitivity report would mix prompts.
                scopes = {_scope(group)} if len(group.split(" · ")) == 3 else {_scope(group), "all"}
                for scope in scopes:
                    count, total, rates = rows.get((scope, metric), (0, 0, []))
                    rates.append(passed / len(expected_repeats))
                    rows[(scope, metric)] = (count + every, total + 1, rates)
    return [
        MetricConsistency(
            scope=scope,
            metric=metric,
            items=total,
            pass_every=count,
            mean_pass_rate=statistics.fmean(rates),
        )
        for (scope, metric), (count, total, rates) in sorted(rows.items())
    ]


def _scope(group: str) -> str:
    """A group without its pack: the mode, the variant and mode, or `all` for one per pack."""
    parts = group.split(" · ")
    rest = [part for index, part in enumerate(parts) if index != _pack_index(parts)]
    return " · ".join(rest) or "all"


def _pack_index(parts: Sequence[str]) -> int:
    # Groups are "variant · pack · mode", "pack · mode" or "pack".
    return 1 if len(parts) == 3 else 0


def markdown(name: str, scores: Consistency) -> str:
    """The scores as two tables, for a terminal or `evals/README.md`."""
    lines = [
        f"### Consistency: {name}",
        "",
        "| Input | Repeats (valid) | Requirements | Every | Some | None | Stories | Problems |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for group in scores.groups:
        reqs = group.requirements
        lines.append(
            f"| {group.group} | {group.repeats} ({group.valid_repeats}) "
            + (
                f"| {reqs.expected} | {_share(reqs.share(reqs.every))} "
                f"| {_share(reqs.share(reqs.some))} | {_share(reqs.share(reqs.none))} "
                if reqs
                else "| | | | "
            )
            + f"| {_range_text(group.stories)} | {_range_text(group.problems)} |"
        )
    lines += [
        "",
        "| Scope | Metric | Items | Pass in every repeat | Mean pass rate |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for metric in scores.metrics:
        lines.append(
            f"| {metric.scope} | {metric.metric} | {metric.items} "
            f"| {metric.pass_every}/{metric.items} ({metric.pass_every_rate:.0%}) "
            f"| {metric.mean_pass_rate:.0%} |"
        )
    return "\n".join(lines) + "\n"


def _share(value: float | None) -> str:
    return "" if value is None else f"{value:.0%}"


def _range_text(value: Range | None) -> str:
    return "" if value is None else f"{value.low} to {value.high} (spread {value.spread})"
