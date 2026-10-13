"""Adapter for providers that speak the OpenAI Chat Completions API (Groq first; ADR 0006).
Per-provider defaults, limits and quirks live in that provider's profile, not here.

Policy enforced here, as in the Gemini adapter:
- No SDK retries (`max_retries=0`); the caller decides whether to try again.
- One model ID and base URL from configuration; no fallback model or provider.
- Reasoning text is not requested or stored; only its token count is kept.
"""

import json
import time
from collections.abc import Mapping, Sequence
from typing import Any, cast

import openai
from openai import OpenAI
from openai.types.chat import ChatCompletion

from scopesteps.agent.domain.model import (
    FinishReason,
    JsonObject,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    ToolCall,
    ToolResults,
    Turn,
    Usage,
    UserMessage,
)

ASSISTANT_STEP = "assistant_message"
SCHEMA_REJECTED = "json_validate_failed"
# Keywords kept when a schema is sent for strict decoding. Validation keywords (lengths, patterns,
# item counts) are dropped: providers support different subsets, and every response is validated
# against the full Pydantic model anyway.
_SCHEMA_KEYWORDS = frozenset(
    {"type", "properties", "required", "items", "enum", "anyOf", "additionalProperties",
     "description", "const"}
)  # fmt: skip
_EFFORT = {"minimal": "low", "low": "low", "medium": "medium", "high": "high"}
_FINISH: dict[str, FinishReason] = {
    "stop": "completed",
    "tool_calls": "tool_calls",
    "length": "max_tokens",
    "content_filter": "blocked",
}


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        model_id: str,
        base_url: str,
        timeout_seconds: float,
        thinking_level: str,
        max_output_tokens_cap: int | None = None,
        reasoning_effort_models: Sequence[str] = (),
    ) -> None:
        self._provider = provider
        self._reasoning_models = tuple(reasoning_effort_models)
        self._model_id = model_id
        self._thinking_level = thinking_level
        self._cap = max_output_tokens_cap
        self._client = OpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout_seconds, max_retries=0
        )

    @property
    def model_id(self) -> str:
        return self._model_id

    def generate(self, request: ModelRequest) -> ModelResult:
        body = build_request_body(
            request, self._model_id, self._thinking_level, self._cap, self._reasoning_models
        )
        started = time.perf_counter()
        try:
            completion = cast(ChatCompletion, self._client.chat.completions.create(**body))
        except openai.BadRequestError as error:
            if _error_code(error) != SCHEMA_REJECTED:
                raise classify_error(error) from error
            # The provider checked the output against the schema and rejected it (for example,
            # cut off at the token limit). That is a bad answer, not a bad request: return it as
            # empty output so validation fails and the caller's single repair handles it.
            latency_ms = round((time.perf_counter() - started) * 1000)
            return _rejected_output(self._provider, self._model_id, latency_ms)
        except openai.OpenAIError as error:
            raise classify_error(error) from error
        latency_ms = round((time.perf_counter() - started) * 1000)
        return parse_completion(completion, self._provider, self._model_id, latency_ms)


def build_request_body(
    request: ModelRequest,
    model_id: str,
    thinking_level: str,
    cap: int | None = None,
    reasoning_models: Sequence[str] = (),
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": request.system_instruction}]
    for turn in request.history:
        messages.extend(_turn_to_messages(turn))
    body: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "max_completion_tokens": min(request.max_output_tokens, cap or request.max_output_tokens),
    }
    if model_id.startswith(tuple(reasoning_models)) and reasoning_models:
        body["reasoning_effort"] = _EFFORT.get(thinking_level, "low")
        body["extra_body"] = {"include_reasoning": False}
    tools = [
        t for t in request.tools if not request.allowed_tools or t.name in request.allowed_tools
    ]
    if tools and request.tool_choice != "none":
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": dict(tool.parameters),
                },
            }
            for tool in tools
        ]
        body["tool_choice"] = _tool_choice(request, [tool.name for tool in tools])
    if request.output_schema is not None:
        # Structured output and tools cannot share a call on these providers; a request that asks
        # for both sends the schema only (tool_choice "none" above already dropped the tools).
        schema, strict = strict_schema(request.output_schema)
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "output", "schema": schema, "strict": strict},
        }
        body.pop("tools", None)
        body.pop("tool_choice", None)
    return body


def _tool_choice(request: ModelRequest, names: Sequence[str]) -> object:
    if request.tool_choice == "any":
        if len(names) == 1:
            return {"type": "function", "function": {"name": names[0]}}
        return "required"
    return "auto"


def _turn_to_messages(turn: Turn) -> list[dict[str, Any]]:
    match turn:
        case UserMessage(text=text):
            return [{"role": "user", "content": text}]
        case ModelTurn(steps=steps):
            return [
                dict(cast(Mapping[str, Any], step["message"]))
                for step in steps
                if step.get("type") == ASSISTANT_STEP
            ]
        case ToolResults(results=results):
            return [
                {
                    "role": "tool",
                    "tool_call_id": result.call_id,
                    "content": json.dumps(result.output),
                }
                for result in results
            ]


def strict_schema(schema: JsonObject) -> tuple[dict[str, Any], bool]:
    """The schema reduced to keywords strict decoding accepts, and whether it qualifies: strict
    mode needs every property required and no additional properties on every object."""
    strict = True

    def reduce(node: Any) -> Any:
        nonlocal strict
        if isinstance(node, list):
            return [reduce(item) for item in cast(list[Any], node)]
        if not isinstance(node, Mapping):
            return node
        mapping = cast(Mapping[str, Any], node)
        reduced: dict[str, Any] = {}
        for key, value in mapping.items():
            if key == "properties":
                reduced[key] = {
                    name: reduce(child) for name, child in cast(Mapping[str, Any], value).items()
                }
            elif key in _SCHEMA_KEYWORDS:
                reduced[key] = reduce(value)
        if "properties" in reduced:
            properties = set(cast(dict[str, Any], reduced["properties"]))
            required = set(cast(list[str], reduced.get("required", [])))
            if required != properties or reduced.get("additionalProperties") is not False:
                strict = False
        return reduced

    return cast(dict[str, Any], reduce(schema)), strict


def parse_completion(completion: Any, provider: str, model_id: str, latency_ms: int) -> ModelResult:
    choices = cast(list[Any], getattr(completion, "choices", None) or [])
    if not choices:
        raise ModelProviderError("malformed_response", "The provider returned no choices")
    choice = choices[0]
    message = choice.message
    calls = cast(list[Any], getattr(message, "tool_calls", None) or [])
    tool_calls = tuple(
        ToolCall(id=str(call.id), name=str(call.function.name), arguments=_arguments(call.function))
        for call in calls
    )
    replayed: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if calls:
        replayed["tool_calls"] = [
            {
                "id": str(call.id),
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in calls
        ]
    reason = str(getattr(choice, "finish_reason", "") or "")
    return ModelResult(
        provider=provider,
        model_id=str(getattr(completion, "model", None) or model_id),
        turn=ModelTurn(steps=({"type": ASSISTANT_STEP, "message": replayed},)),
        text=message.content,
        tool_calls=tool_calls,
        finish_reason="tool_calls" if tool_calls else _FINISH.get(reason, "other"),
        usage=_usage(getattr(completion, "usage", None)),
        latency_ms=latency_ms,
        provider_status=reason,
    )


def _arguments(function: Any) -> JsonObject:
    """Malformed arguments reach the tool as an invalid payload, so the model gets an error
    result it can correct instead of the whole step failing."""
    try:
        parsed = json.loads(function.arguments or "{}")
    except ValueError:
        return {"unparseable_arguments": str(function.arguments)}
    return cast(JsonObject, parsed) if isinstance(parsed, dict) else {"arguments": parsed}


def _usage(usage: Any) -> Usage:
    if usage is None:
        return Usage()
    completion = int(getattr(usage, "completion_tokens", None) or 0)
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = int(getattr(details, "reasoning_tokens", None) or 0)
    return Usage(
        input_tokens=int(getattr(usage, "prompt_tokens", None) or 0),
        # Completion tokens include reasoning; keep them apart so both are billed as output.
        output_tokens=completion - reasoning,
        thinking_tokens=reasoning,
        total_tokens=int(getattr(usage, "total_tokens", None) or 0),
    )


def classify_error(error: openai.OpenAIError) -> ModelProviderError:
    """Map SDK failures to a kind. Messages are generic: error bodies can echo request content."""
    if isinstance(error, openai.APITimeoutError):
        return ModelProviderError("timeout", "The model provider did not respond in time")
    if isinstance(error, openai.APIConnectionError):
        return ModelProviderError("unavailable", "Could not reach the model provider")
    if not isinstance(error, openai.APIStatusError):
        return ModelProviderError("malformed_response", "Unexpected provider response")
    status = error.status_code
    label = f"HTTP {status}"
    # 413 is how Groq reports a request larger than the per-minute token allowance.
    if status in {429, 413}:
        return ModelProviderError(
            "quota",
            f"Model quota or rate limit reached ({label})",
            retry_after_seconds=_retry_after(error),
            status_code=status,
        )
    if status in {401, 403}:
        return ModelProviderError(
            "auth", f"Model provider rejected the credentials ({label})", status_code=status
        )
    if status == 408:
        return ModelProviderError("timeout", f"Model request timed out ({label})", status_code=408)
    if status >= 500:
        return ModelProviderError(
            "unavailable", f"Model provider unavailable ({label})", status_code=status
        )
    return ModelProviderError(
        "invalid_request", f"Model provider rejected the request ({label})", status_code=status
    )


def _error_code(error: openai.APIStatusError) -> str:
    raw: object = error.body
    body = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    inner: object = body.get("error", body)
    return str(cast(dict[str, Any], inner).get("code", "")) if isinstance(inner, dict) else ""


def _rejected_output(provider: str, model_id: str, latency_ms: int) -> ModelResult:
    return ModelResult(
        provider=provider,
        model_id=model_id,
        turn=ModelTurn(
            steps=({"type": ASSISTANT_STEP, "message": {"role": "assistant", "content": ""}},)
        ),
        text="",
        tool_calls=(),
        finish_reason="other",
        usage=Usage(),
        latency_ms=latency_ms,
        provider_status=SCHEMA_REJECTED,
        warnings=("output rejected by the provider's schema check; usage not reported",),
    )


def _retry_after(error: openai.APIStatusError) -> float | None:
    value = error.response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
