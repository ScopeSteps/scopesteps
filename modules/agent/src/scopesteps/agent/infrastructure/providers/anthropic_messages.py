"""Adapter for Anthropic's Messages API, through the official `anthropic` SDK 1.x (ADR 0032).

Policy enforced here, not left to SDK defaults:
- No SDK retries (`max_retries=0`); the caller decides whether to try again.
- Every call is streamed, so a long output does not hit an HTTP timeout.
- `thinking` is omitted, so the model thinks adaptively; effort comes from the step's binding, and
  no sampling parameters are sent. The server-side refusal fallback is not used.
- The history is append-only, so thinking blocks stay valid and go back exactly as received:
  every call of a step sends the same system prompt and tools, and a call that may use only some
  of them says so through `tool_choice` or an appended system message (see `build_request_params`).
- An output schema the API cannot compile for strict decoding fails as `schema_too_complex`; the
  caller sends it again with `strict_output=False` (see `StepModel`). The adapter remembers the
  schema and sends it that way from then on, so the refused request is not repeated.
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
SYSTEM_STEP = "scopesteps_system"
"""A step of our own in `ModelTurn.steps`: the system message appended before the call that
produced the turn. It goes back as that message, before the turn, on every later call."""
DEFAULT_TIMEOUT_SECONDS = 600.0
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
# The messages the API returns when a schema's compiled grammar exceeds its limits.
_SCHEMA_TOO_COMPLEX_MESSAGE = re.compile(
    r"grammar is too large|too complex for compilation|exceeds complexity"
)
SCHEMA_AS_INSTRUCTIONS = (
    "Answer with one JSON object and nothing else: no code fence and no text before or after it. "
    "It must match this JSON Schema:"
)
"""Opens the system message that carries the output schema when strict decoding is off."""
NOT_STRICT_WARNING = "the output schema was sent as instructions, without strict decoding"


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
        self._too_complex: set[str] = set()
        """Fingerprints of requests whose output schema the API refused to compile."""

    def generate(self, request: ModelRequest) -> ModelResult:
        if request.model is None:
            raise ModelProviderError("invalid_request", "No model was named for the call")
        model = request.model
        key = _schema_key(request) if request.output_schema is not None else None
        if key in self._too_complex:
            request = replace(request, strict_output=False)
        params, note = build_request_params(request, CATALOG.capabilities(model))
        timeout = request.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        started = time.perf_counter()
        try:
            with self._client.messages.stream(**params, timeout=timeout) as stream:
                message = stream.get_final_message()
                request_id = stream.request_id or ""
        except anthropic.AnthropicError as error:
            failure = classify_error(error)
            if failure.kind == "schema_too_complex" and key is not None:
                self._too_complex.add(key)
            raise failure from error
        except httpx2.TransportError as error:
            # The SDK wraps network failures only until the response starts; one while the stream
            # is being read surfaces as the transport's own error.
            raise classify_transport_error(error) from error
        latency_ms = round((time.perf_counter() - started) * 1000)
        return parse_message(message, request, note, latency_ms, request_id)


def _schema_key(request: ModelRequest) -> str:
    """What the API compiles for one request: its output schema and its strict tools."""
    compiled = {
        "schema": request.output_schema,
        "tools": [(tool.name, tool.parameters) for tool in request.tools],
    }
    return hashlib.sha256(json.dumps(compiled, sort_keys=True).encode()).hexdigest()


def build_request_params(
    request: ModelRequest, capabilities: ModelCapabilities | None
) -> tuple[dict[str, Any], str | None]:
    """The Messages API parameters, and the system message appended for this call, if any.

    Every tool is sent on every call. Changing the system prompt or tools within a step would make
    the API refuse the thinking blocks already in the history, so `allowed_tools` narrows a call
    another way: a forced choice of the one tool where the model accepts it (Haiku 5.5, whose
    forced call then has no thinking), and otherwise a system message after the last user turn,
    kept in the history from then on. Step code still checks which tool was called.

    An unknown model is assumed to refuse a forced tool choice, the safe side: the prompt asks for
    the tool call instead.

    With `strict_output=False` the output schema goes in that appended system message instead of
    `output_config.format`, so the system prompt stays the same as on the step's strict calls.
    """
    system_text = request.system_instruction
    tools = request.tools
    forced = bool(capabilities and capabilities.supports_forced_tool_choice)
    allowed = [tool.name for tool in tools if tool.name in request.allowed_tools]
    narrowed = bool(allowed) and len(allowed) < len(tools)
    one = narrowed and len(allowed) == 1 and request.tool_choice == "any" and forced
    tool_choice: dict[str, str] | None = None
    note: str | None = None
    if tools:
        if request.tool_choice == "none":
            tool_choice = {"type": "none"}
        elif one:
            tool_choice = {"type": "tool", "name": allowed[0]}
        elif request.tool_choice == "any" and forced:
            tool_choice = {"type": "any"}
        else:
            tool_choice = {"type": "auto"}
            if request.tool_choice == "any":
                # The same for every call of the step, so the system prompt does not change.
                system_text = f"{system_text}\n\n{ANSWER_WITH_A_TOOL}"
        if narrowed and not one and request.tool_choice != "none":
            note = only_these_tools(allowed)
    if request.output_schema is not None and not request.strict_output:
        instructions = schema_as_instructions(request.output_schema)
        note = instructions if note is None else f"{note}\n\n{instructions}"
    system: list[dict[str, Any]] = [{"type": "text", "text": system_text}]
    messages = _messages(request.history)
    _add_cache_breakpoint(system, messages)
    if note is not None:
        messages.append({"role": "system", "content": note})

    params: dict[str, Any] = {
        "model": request.model,
        "max_tokens": request.max_output_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        params["tools"] = [_tool_param(tool) for tool in tools]
    if tool_choice is not None:
        params["tool_choice"] = tool_choice
    output_config: dict[str, Any] = {}
    if request.effort is not None:
        output_config["effort"] = request.effort
    if request.output_schema is not None and request.strict_output:
        output_config["format"] = {
            "type": "json_schema",
            "schema": strip_schema(request.output_schema),
        }
    if output_config:
        params["output_config"] = output_config
    return params, note


def only_these_tools(names: Sequence[str]) -> str:
    """The system message that narrows one call to some of the step's tools."""
    listed = ", ".join(f"`{name}`" for name in names)
    return f"On this turn you may call only {listed}. Do not call any other tool."


def schema_as_instructions(schema: JsonObject) -> str:
    """The system message that asks for output against a schema strict decoding cannot take."""
    return f"{SCHEMA_AS_INSTRUCTIONS}\n{json.dumps(schema, separators=(',', ':'))}"


def json_object_text(text: str) -> str:
    """The JSON object in an answer written without strict decoding: from its first `{` to its
    last `}`, which drops a code fence or a sentence around it. Validation judges the rest."""
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if 0 <= start < end else text


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


def _messages(history: Sequence[Turn]) -> list[dict[str, Any]]:
    """The history as Messages API turns, exactly as sent and received before. A system message
    appended for an earlier call goes back before the turn it produced."""
    messages: list[dict[str, Any]] = []
    for turn in history:
        match turn:
            case UserMessage(text=text):
                messages.append({"role": "user", "content": [{"type": "text", "text": text}]})
            case ModelTurn(steps=steps):
                messages.extend(
                    {"role": "system", "content": str(step.get("text"))}
                    for step in steps
                    if step.get("type") == SYSTEM_STEP
                )
                content = [dict(step) for step in steps if step.get("type") != SYSTEM_STEP]
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
    message: Any,
    request: ModelRequest,
    note: str | None,
    latency_ms: int,
    request_id: str = "",
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
    text = "".join(texts) if texts else None
    status, warnings = stop_reason, ()
    if request.output_schema is not None and not request.strict_output:
        warnings = (NOT_STRICT_WARNING,)
        text = json_object_text(text) if text is not None else None
    if request.tool_choice == "any" and request.tools and not tool_calls and finish == "completed":
        # Bad output, not a failed request: the step's single repair asks again.
        finish, status = "other", NO_TOOL_CALL
        warnings = (*warnings, "answered without the required tool call")
    return ModelResult(
        provider=PROVIDER,
        model_id=str(getattr(message, "model", None) or request.model),
        turn=ModelTurn(
            steps=(*blocks, {"type": SYSTEM_STEP, "text": note})
            if note is not None
            else tuple(blocks)
        ),
        text=text,
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


def classify_transport_error(error: httpx2.TransportError) -> ModelProviderError:
    """Map a network failure while the answer streams in, as the SDK does for one before it."""
    if isinstance(error, httpx2.TimeoutException):
        return ModelProviderError("timeout", "The model provider did not respond in time")
    return ModelProviderError("unavailable", "The connection to the model provider was lost")


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
    if status == 400 and _SCHEMA_TOO_COMPLEX_MESSAGE.search(markers):
        return fail("schema_too_complex", "The provider could not compile the output schema")
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
