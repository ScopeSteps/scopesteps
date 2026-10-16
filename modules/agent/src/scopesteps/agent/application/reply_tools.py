"""The read-only tools a reply may call (prompt `reply-v2`, ADR 0010 notes).

Every tool only reads what the reply run already holds: its pinned source paragraphs, recorded
answers and the project's backlog. Arguments are limited by enum to the labels the model was
shown, and code checks them again, so an id from another project or an invented one comes back
as a tool error the model can act on. Results are fenced and escaped like sources.
"""

import copy
import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from scopesteps.agent.application.schemas import (
    GetStoryArgs,
    ListOpenDecisionsArgs,
    LookupSourceArgs,
    SourceBlockInput,
    provider_schema,
)
from scopesteps.agent.application.tools import LOOKUP_SOURCE, fence
from scopesteps.agent.domain.model import ToolCall, ToolResult, ToolSpec
from scopesteps.backlog.client import BacklogOutline, ItemId, OutlineDecision, OutlineItem

GET_STORY = "get_story"
LIST_OPEN_DECISIONS = "list_open_decisions"
MAX_LOOKUPS = 3
"""Tool calls a reply may make before it must answer. A fourth is refused by code."""


@dataclass(frozen=True)
class BacklogLabels:
    """The backlog under the labels a reply's model sees: epics E1.., stories S1.. and open
    decisions D1.., in the version's order."""

    items: Mapping[str, OutlineItem]
    decisions: Mapping[str, OutlineDecision]

    def label_of_id(self) -> dict[ItemId, str]:
        return {item.id: label for label, item in self.items.items() if item.id is not None}

    def names(self) -> dict[str, str]:
        """Each label by what people see: an item's title in quotes, a decision's subject."""
        return {
            **{label: f'"{item.title}"' for label, item in self.items.items()},
            **{label: f'the open decision "{d.subject}"' for label, d in self.decisions.items()},
        }


NO_BACKLOG = BacklogLabels({}, {})


def label_backlog(outline: BacklogOutline | None) -> BacklogLabels:
    if outline is None:
        return NO_BACKLOG
    items: dict[str, OutlineItem] = {}
    counts = {"epic": 0, "story": 0}
    for item in outline.items:
        counts[item.kind] += 1
        items[f"{'E' if item.kind == 'epic' else 'S'}{counts[item.kind]}"] = item
    decisions = {f"D{index}": d for index, d in enumerate(outline.decisions, start=1)}
    return BacklogLabels(items, decisions)


@dataclass(frozen=True)
class Lookups:
    """What the reply's tools may read."""

    blocks: Sequence[SourceBlockInput]
    backlog: BacklogLabels


@dataclass(frozen=True)
class LookupOutcome:
    result: ToolResult
    found: int
    """How many blocks, items or decisions the result holds; recorded on the step."""


def lookup_specs(lookups: Lookups) -> tuple[ToolSpec, ...]:
    """The lookup tools for this reply, each argument limited to the labels it was shown.
    `get_story` is offered only when there is a backlog, since an enum cannot be empty."""
    specs = [
        ToolSpec(
            name=LOOKUP_SOURCE.name,
            description=(
                "Re-read source paragraphs or recorded answers by id, or search them by words. "
                "Read-only."
            ),
            parameters=_with_enum(
                provider_schema(LookupSourceArgs), "block_ids", [b.id for b in lookups.blocks]
            ),
        ),
        ToolSpec(
            name=LIST_OPEN_DECISIONS,
            description=(
                "List the backlog's decisions nobody has answered yet, with the items each "
                "blocks. Read-only."
            ),
            parameters=provider_schema(ListOpenDecisionsArgs),
        ),
    ]
    if lookups.backlog.items:
        specs.insert(
            1,
            ToolSpec(
                name=GET_STORY,
                description=(
                    "Get one backlog item by its label: title, description, acceptance criteria "
                    "and the open decisions that block it. Read-only."
                ),
                parameters=_with_enum(
                    provider_schema(GetStoryArgs), "item_id", list(lookups.backlog.items)
                ),
            ),
        )
    return tuple(specs)


def run_lookup(call: ToolCall, lookups: Lookups) -> LookupOutcome:
    """Execute one lookup. Mistakes come back as error results the model can act on."""
    match call.name:
        case LOOKUP_SOURCE.name:
            return _lookup_source(call, lookups.blocks)
        case name if name == GET_STORY and lookups.backlog.items:
            return _get_story(call, lookups.backlog)
        case name if name == LIST_OPEN_DECISIONS:
            return _list_open_decisions(call, lookups.backlog)
        case _:
            return LookupOutcome(tool_error(call, f"Tool {call.name!r} is not available."), 0)


def tool_error(call: ToolCall, message: str) -> ToolResult:
    return ToolResult(call.id, call.name, {"error": message}, is_error=True)


def _lookup_source(call: ToolCall, blocks: Sequence[SourceBlockInput]) -> LookupOutcome:
    args = _parse(call, LookupSourceArgs)
    if isinstance(args, ToolResult):
        return LookupOutcome(args, 0)
    by_id = {block.id: block for block in blocks}
    unknown = [block_id for block_id in args.block_ids if block_id not in by_id]
    if unknown:
        return LookupOutcome(tool_error(call, _not_one_of("block_ids", unknown, list(by_id))), 0)
    if args.block_ids:
        found = [by_id[block_id] for block_id in args.block_ids]
    else:
        words = args.query.lower().split()
        found = [b for b in blocks if all(word in b.text.lower() for word in words)][: args.limit]
    output = {"blocks": [fence(block) for block in found]}
    return LookupOutcome(ToolResult(call.id, call.name, output), len(found))


def _get_story(call: ToolCall, backlog: BacklogLabels) -> LookupOutcome:
    args = _parse(call, GetStoryArgs)
    if isinstance(args, ToolResult):
        return LookupOutcome(args, 0)
    item = backlog.items.get(args.item_id)
    if item is None:
        message = _not_one_of("item_id", [args.item_id], list(backlog.items))
        return LookupOutcome(tool_error(call, message), 0)
    labels = backlog.label_of_id()
    parent = "" if item.parent_id is None else labels.get(item.parent_id, "")
    blocking = [
        f"- {label}: {d.subject}. {d.question}"
        for label, d in backlog.decisions.items()
        if item.id is not None and item.id in d.affected_item_ids
    ]
    lines = [
        f"title: {item.title}",
        f"description: {item.description}",
        "acceptance criteria:",
        *(f"- {criterion}" for criterion in item.criteria),
        "open decisions blocking it:",
        *(blocking or ["- none"]),
    ]
    parent_attribute = f' parent="{parent}"' if parent else ""
    text = (
        f'<item id="{args.item_id}" kind="{item.kind}"{parent_attribute}>\n'
        f"{_escape(chr(10).join(lines))}\n</item>"
    )
    return LookupOutcome(ToolResult(call.id, call.name, {"item": text}), 1)


def _list_open_decisions(call: ToolCall, backlog: BacklogLabels) -> LookupOutcome:
    args = _parse(call, ListOpenDecisionsArgs)
    if isinstance(args, ToolResult):
        return LookupOutcome(args, 0)
    labels = backlog.label_of_id()
    decisions: list[str] = []
    for label, d in backlog.decisions.items():
        blocks = " ".join(labels[item] for item in d.affected_item_ids if item in labels)
        decisions.append(
            f'<decision id="{label}" blocks="{blocks}">'
            f"{_escape(f'{d.subject}. {d.question}')}</decision>"
        )
    output: dict[str, object] = {"decisions": decisions}
    if not decisions:
        output["note"] = "No decision is open." if backlog.items else "There is no backlog yet."
    return LookupOutcome(ToolResult(call.id, call.name, output), len(decisions))


def _parse[Args: BaseModel](call: ToolCall, model: type[Args]) -> Args | ToolResult:
    try:
        return model.model_validate(call.arguments)
    except ValidationError as failure:
        return tool_error(
            call,
            "; ".join(
                f"{'.'.join(str(part) for part in item['loc']) or 'arguments'}: {item['msg']}"
                for item in failure.errors()[:5]
            ),
        )


def _not_one_of(field: str, given: Sequence[str], allowed: Sequence[str]) -> str:
    return (
        f"{field}: {', '.join(repr(value) for value in given)} is not one of "
        f"{', '.join(allowed) or '(none)'}. Use the ids exactly as given."
    )


def _with_enum(schema: dict[str, Any], field: str, ids: Sequence[str]) -> dict[str, Any]:
    """`schema` with property `field` (a string or a list of strings) limited to `ids`."""
    constrained = copy.deepcopy(schema)
    if not ids:
        return constrained
    properties = cast(dict[str, Any], constrained["properties"])
    node = cast(dict[str, Any], properties[field])
    if node.get("type") == "array":
        node["items"] = {**cast(dict[str, Any], node.get("items", {})), "enum": list(ids)}
    else:
        node["enum"] = list(ids)
    return constrained


def _escape(text: str) -> str:
    return html.escape(text, quote=False)
