"""Adapter for Anthropic's Messages API, through the official `anthropic` SDK 1.x (ADR 0032).

Policy enforced here, not left to SDK defaults:
- No SDK retries (`max_retries=0`); the caller decides whether to try again.
- Every call is streamed, so a long output does not hit an HTTP timeout.
- `thinking` is omitted, so the model thinks adaptively; effort comes from the step's binding, and
  no sampling parameters are sent. The server-side refusal fallback is not used.
- Assistant content, thinking blocks included, is kept exactly as received and sent back
  unchanged, unless the step itself changed the system prompt or tools since (see `_messages`).
"""

import hashlib
import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

import anthropic
import httpx2

from scopesteps.agent.domain.model import (
    FinishReason,
    JsonObject,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    ProviderErrorKind,
    ToolCall,
    ToolResults,
    ToolSpec,
    Turn,
    Usage,
    UserMessage,
)
from scopesteps.agent.domain.providers import ModelCapabilities
from scopesteps.agent.infrastructure.providers.anthropic import CATALOG, PROVIDER

ANSWER_WITH_A_TOOL = "Answer only by calling a tool."
"""Added to the system prompt when a request must end in a tool call but the model refuses a
forced tool choice."""
NO_TOOL_CALL = "no_tool_call"
PREFIX_STEP = "scopesteps_prefix"
"""A step of our own in `ModelTurn.steps`, never sent: the digest of the system prompt and tools
the turn was produced under."""
DEFAULT_TIMEOUT_SECONDS = 600.0
_THINKING_TYPES = frozenset({"thinking", "redacted_thinking"})
_FINISH: dict[str, FinishReason] = {
    "end_turn": "completed",
    "tool_use": "tool_calls",
    "max_tokens": "max_tokens",
    "refusal": "blocked",
}
# What structured outputs and strict tools accept. Everything else (lengths, item counts beyond
# 0 or 1, numeric bounds, patterns) is dropped: the API refuses it, and every response is still
# validated against the full Pydantic model.
_SCHEMA_KEYWORDS = frozenset(
    {"type", "properties", "required", "items", "enum", "const", "anyOf", "allOf", "$ref",
     "$defs", "description", "additionalProperties", "format", "minItems"}
)  # fmt: skip
_STRING_FORMATS = frozenset(
    {"date-time", "time", "date", "duration", "email", "hostname", "uri", "ipv4", "ipv6", "uuid"}
)
_SPEND_LIMIT_MESSAGE = re.compile(r"reached your specified .*usage limits")


class AnthropicMessagesProvider:
    """One instance serves every Anthropic model: each request names its own (`request.model`)."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        http_client: httpx2.Client | None = None,
    ) -> None:
        self._client = anthropic.Anthropic(
            api_key=api_key, base_url=base_url, http_client=http_client, max_retries=0
        )

    def generate(self, request: ModelRequest) -> ModelResult:
        if request.model is None:
            raise ModelProviderError("invalid_request", "No model was named for the call")
        params, digest = build_request_params(request, CATALOG.capabilities(request.model))
        timeout = request.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        started = time.perf_counter()
        try:
            with self._client.messages.stream(**params, timeout=timeout) as stream:
                message = stream.get_final_message()
                request_id = stream.request_id or ""
        except anthropic.AnthropicError as error:
            raise classify_error(error) from error
        latency_ms = round((time.perf_counter() - started) * 1000)
        return parse_message(message, request, digest, latency_ms, request_id)


def build_request_params(
    request: ModelRequest, capabilities: ModelCapabilities | None
) -> tuple[dict[str, Any], str]:
    """The Messages API parameters, and the digest of the system prompt and tools they carry.

    An unknown model is assumed to refuse a forced tool choice, the safe side: the prompt asks for
    the tool call instead.
    """
    system_text = request.system_instruction
    tools = [
        tool
        for tool in request.tools
        if not request.allowed_tools or tool.name in request.allowed_tools
    ]
    tool_choice: dict[str, str] | None = None
    if tools:
        if request.tool_choice == "none":
            tool_choice = {"type": "none"}
        elif (
            request.tool_choice == "any"
            and capabilities
            and capabilities.supports_forced_tool_choice
        ):
            tool_choice = {"type": "any"}
        else:
            tool_choice = {"type": "auto"}
            if request.tool_choice == "any":
                system_text = f"{system_text}\n\n{ANSWER_WITH_A_TOOL}"
    tool_params = [_tool_param(tool) for tool in tools]
    digest = _prefix_digest(system_text, tool_params)
    system: list[dict[str, Any]] = [{"type": "text", "text": system_text}]
    messages = _messages(request.history, digest)
    _add_cache_breakpoint(system, messages)

    params: dict[str, Any] = {
        "model": request.model,
        "max_tokens": request.max_output_tokens,
        "system": system,
        "messages": messages,
    }
    if tool_params:
        params["tools"] = tool_params
    if tool_choice is not None:
        params["tool_choice"] = tool_choice
    output_config: dict[str, Any] = {}
    if request.effort is not None:
        output_config["effort"] = request.effort
    if request.output_schema is not None:
        output_config["format"] = {
            "type": "json_schema",
            "schema": strip_schema(request.output_schema),
        }
    if output_config:
        params["output_config"] = output_config
    return params, digest


def _tool_param(tool: ToolSpec) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": strip_schema(tool.parameters),
        "strict": True,
    }


def strip_schema(schema: JsonObject) -> dict[str, Any]:
    """The schema reduced to what structured outputs accept, with every object closed
    (`additionalProperties: false`), as strict decoding requires."""

    def reduce(node: Any) -> Any:
        if isinstance(node, list):
            return [reduce(item) for item in cast(list[Any], node)]
        if not isinstance(node, Mapping):
            return node
        reduced: dict[str, Any] = {}
        for key, value in cast(Mapping[str, Any], node).items():
            if key in {"properties", "$defs"}:
                reduced[key] = {
                    name: reduce(child) for name, child in cast(Mapping[str, Any], value).items()
                }
            elif key == "format":
                if value in _STRING_FORMATS:
                    reduced[key] = value
            elif key == "minItems":
                if value in (0, 1):
                    reduced[key] = value
            elif key == "additionalProperties":
                continue
            elif key in _SCHEMA_KEYWORDS:
                reduced[key] = reduce(value)
        if reduced.get("type") == "object" or "properties" in reduced:
            reduced["additionalProperties"] = False
        return reduced

    return cast(dict[str, Any], reduce(schema))


def _prefix_digest(system_text: str, tools: Sequence[Mapping[str, Any]]) -> str:
    canonical = json.dumps([system_text, list(tools)], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _messages(history: Sequence[Turn], digest: str) -> list[dict[str, Any]]:
    """The history as Messages API turns.

    A thinking block is valid only while the system prompt, tools and earlier messages that
    produced it are unchanged; replaying one after a change is refused. A step that narrows its
    tools for a last call (a reply's final turn) changes that prefix, so from the first turn
    produced under a different prefix on, thinking blocks are left out. Everything else is sent
    exactly as received.
    """
    messages: list[dict[str, Any]] = []
    changed = False
    for turn in history:
        match turn:
            case UserMessage(text=text):
                messages.append({"role": "user", "content": [{"type": "text", "text": text}]})
            case ModelTurn(steps=steps):
                produced_under = next(
                    (str(step.get("sha256")) for step in steps if step.get("type") == PREFIX_STEP),
                    None,
                )
                changed = changed or (produced_under is not None and produced_under != digest)
                content = [
                    dict(step)
                    for step in steps
                    if step.get("type") != PREFIX_STEP
                    and not (changed and step.get("type") in _THINKING_TYPES)
                ]
                if content:
                    messages.append({"role": "assistant", "content": content})
            case ToolResults(results=results):
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": result.call_id,
                                "content": json.dumps(result.output),
                                "is_error": result.is_error,
                            }
                            for result in results
                        ],
                    }
                )
    return messages


def _add_cache_breakpoint(system: list[dict[str, Any]], messages: list[dict[str, Any]]) -> None:
    """One breakpoint, after the stable prefix: the system prompt and the step's first user
    message, which carries the sources and stays the same for every call of the step. Turns added
    during the step come after it."""
    first_user = next((m for m in messages if m["role"] == "user"), None)
    blocks = cast(list[dict[str, Any]], first_user["content"]) if first_user else system
    blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}


def parse_message(
    message: Any, request: ModelRequest, digest: str, latency_ms: int, request_id: str = ""
) -> ModelResult:
    blocks = [
        cast(dict[str, Any], block.to_dict(mode="json"))
        for block in cast(list[Any], message.content)
    ]
    tool_calls = tuple(
        ToolCall(
            id=str(block["id"]),
            name=str(block["name"]),
            arguments=cast(JsonObject, block.get("input") or {}),
        )
        for block in blocks
        if block.get("type") == "tool_use"
    )
    texts = [str(block["text"]) for block in blocks if block.get("type") == "text"]
    stop_reason = str(getattr(message, "stop_reason", "") or "")
    finish: FinishReason = "tool_calls" if tool_calls else _FINISH.get(stop_reason, "other")
    status, warnings = stop_reason, ()
    if request.tool_choice == "any" and request.tools and not tool_calls and finish == "completed":
        # Bad output, not a failed request: the step's single repair asks again.
        finish, status = "other", NO_TOOL_CALL
        warnings = ("answered without the required tool call",)
    return ModelResult(
        provider=PROVIDER,
        model_id=str(getattr(message, "model", None) or request.model),
        turn=ModelTurn(steps=(*blocks, {"type": PREFIX_STEP, "sha256": digest})),
        text="".join(texts) if texts else None,
        tool_calls=tool_calls,
        finish_reason=finish,
        usage=_usage(getattr(message, "usage", None)),
        latency_ms=latency_ms,
        provider_status=status,
        warnings=warnings,
        request_id=request_id,
    )


def _usage(usage: Any) -> Usage:
    if usage is None:
        return Usage()

    def count(source: Any, name: str) -> int:
        return int(getattr(source, name, None) or 0)

    output = count(usage, "output_tokens")
    # Output includes thinking; keep them apart so both are reported and billed as output.
    thinking = min(count(getattr(usage, "output_tokens_details", None), "thinking_tokens"), output)
    usage_counts = Usage(
        input_tokens=count(usage, "input_tokens"),
        output_tokens=output - thinking,
        thinking_tokens=thinking,
        cache_read_tokens=count(usage, "cache_read_input_tokens"),
        cache_write_tokens=count(usage, "cache_creation_input_tokens"),
    )
    total = (
        usage_counts.input_tokens
        + usage_counts.cache_read_tokens
        + usage_counts.cache_write_tokens
        + output
    )
    return replace(usage_counts, total_tokens=total)


def classify_error(error: anthropic.AnthropicError) -> ModelProviderError:
    """Map an SDK failure to a kind. Messages are generic and carry the request id, never the
    response body, which can echo request content."""
    if isinstance(error, anthropic.APITimeoutError):
        return ModelProviderError("timeout", "The model provider did not respond in time")
    if isinstance(error, anthropic.APIConnectionError):
        return ModelProviderError("unavailable", "Could not reach the model provider")
    if not isinstance(error, anthropic.APIStatusError):
        return ModelProviderError("malformed_response", "Unexpected provider response")
    status, request_id = error.status_code, error.request_id
    markers = _markers(error.body)
    label = f"HTTP {status}" + (f", request {request_id}" if request_id else "")

    def fail(
        kind: ProviderErrorKind, what: str, retry_after: float | None = None
    ) -> ModelProviderError:
        return ModelProviderError(
            kind,
            f"{what} ({label})",
            retry_after_seconds=retry_after,
            status_code=status,
            request_id=request_id,
        )

    if status < 400:
        # An error event inside a stream that had already answered 200.
        status_by_type = {
            "rate_limit_error": 429,
            "overloaded_error": 529,
            "api_error": 500,
            "timeout_error": 504,
        }
        status = status_by_type.get(str(error.type or ""), 500)
    if "enforced_spend_limit_reached" in markers or (
        status == 400 and _SPEND_LIMIT_MESSAGE.search(markers)
    ):
        return fail("spend_limit", "The provider account reached its spend limit")
    if status == 429:
        return fail("quota", "Model rate limit reached", _retry_after(error.response))
    if status == 413:
        return fail("request_too_large", "The request is larger than the provider accepts")
    if status in {401, 402, 403}:
        return fail("auth", "Model provider rejected the credentials or billing")
    if status in {408, 504}:
        return fail("timeout", "Model request timed out")
    if status >= 500:
        return fail("unavailable", "Model provider unavailable")
    return fail("invalid_request", "Model provider rejected the request")


def _markers(body: object) -> str:
    """The error's type, code and message in lower case, for matching documented markers only."""
    error = cast(Mapping[str, object], body).get("error") if isinstance(body, Mapping) else None
    if not isinstance(error, Mapping):
        return ""
    fields = cast(Mapping[str, object], error)
    return " ".join(str(fields.get(key) or "") for key in ("type", "code", "message")).lower()


def _retry_after(response: httpx2.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
