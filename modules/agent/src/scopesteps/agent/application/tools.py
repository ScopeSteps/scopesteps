"""The agent's tools. Each is typed, narrow and read-only or pausing: none can approve, publish,
change permissions or reach outside the run's pinned sources."""

import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from scopesteps.agent.application.schemas import (
    LookupSourceArgs,
    RequestClarificationArgs,
    SourceBlockInput,
    provider_schema,
)
from scopesteps.agent.domain.model import JsonObject, ToolCall, ToolResult, ToolSpec

LOOKUP_SOURCE = ToolSpec(
    name="lookup_source",
    description=(
        "Search the project's source blocks. Read-only. Returns matching blocks with their IDs "
        "and text. Use block_ids to fetch exact blocks, or query to search by words."
    ),
    parameters=provider_schema(LookupSourceArgs),
)
REQUEST_CLARIFICATION = ToolSpec(
    name="request_clarification",
    description=(
        "Ask the reviewer questions whose answers would change the scope: a conflict, a missing "
        "decision or a vague requirement. Cite the blocks each question is about. The run pauses "
        "until the reviewer answers or skips each question; answers come back as this tool's "
        "result."
    ),
    parameters=provider_schema(RequestClarificationArgs),
)
VALIDATE_BACKLOG = "validate_backlog"
"""Runs the single-pass draft checks on the typed draft. Executed by the harness on every draft,
so the model cannot skip it; recorded as a tool step."""


@dataclass(frozen=True)
class Clarification:
    call_id: str
    args: RequestClarificationArgs


def run_tool(
    call: ToolCall, blocks: Sequence[SourceBlockInput], *, may_ask: bool
) -> ToolResult | Clarification:
    """Execute one tool call. Mistakes come back as error results the model can act on."""
    match call.name:
        case LOOKUP_SOURCE.name:
            return _lookup_source(call, blocks)
        case REQUEST_CLARIFICATION.name if may_ask:
            return _request_clarification(call, blocks)
        case REQUEST_CLARIFICATION.name:
            return _error(call, "No clarification rounds are left. Reply READY to draft.")
        case _:
            return _error(call, f"Tool {call.name!r} is not available.")


def fence(block: SourceBlockInput) -> str:
    """Tool results carry source text, so they get the same escaped fencing as prompt sources."""
    return (
        f'<source id="{block.id}" label="{html.escape(block.label)}">'
        f"{html.escape(block.text, quote=False)}</source>"
    )


def _lookup_source(call: ToolCall, blocks: Sequence[SourceBlockInput]) -> ToolResult:
    try:
        args = LookupSourceArgs.model_validate(call.arguments)
    except ValidationError as error:
        return _error(call, _summarize(error))
    by_id = {block.id: block for block in blocks}
    if args.block_ids:
        found = [by_id[block_id] for block_id in args.block_ids if block_id in by_id]
        missing = [block_id for block_id in args.block_ids if block_id not in by_id]
    else:
        words = args.query.lower().split()
        found = [b for b in blocks if all(word in b.text.lower() for word in words)][: args.limit]
        missing = []
    output: dict[str, object] = {"blocks": [fence(block) for block in found]}
    if missing:
        output["not_found"] = missing
    return ToolResult(call.id, call.name, output)


def _request_clarification(
    call: ToolCall, blocks: Sequence[SourceBlockInput]
) -> ToolResult | Clarification:
    try:
        args = RequestClarificationArgs.model_validate(call.arguments)
    except ValidationError as error:
        return _error(call, _summarize(error))
    known = {block.id for block in blocks}
    unknown = sorted(
        {block_id for q in args.questions for block_id in q.block_ids if block_id not in known}
    )
    if unknown:
        return _error(call, f"Unknown block ids: {', '.join(unknown)}. Cite blocks as given.")
    return Clarification(call.id, args)


def _error(call: ToolCall, message: str) -> ToolResult:
    output: Mapping[str, object] = {"error": message}
    return ToolResult(call.id, call.name, output, is_error=True)


def _summarize(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'arguments'}: {item['msg']}"
        for item in error.errors()[:5]
    )


def answers_output(answers: Sequence[SourceBlockInput]) -> JsonObject:
    """The deferred result of `request_clarification`: each answer or open decision, fenced."""
    return {
        "answers": [fence(block) for block in answers],
        "note": (
            "Blocks labelled 'reviewer answer' are decisions confirmed by an authorized reviewer; "
            "cite them like sources. Blocks labelled 'open decision' remain unresolved."
        ),
    }
