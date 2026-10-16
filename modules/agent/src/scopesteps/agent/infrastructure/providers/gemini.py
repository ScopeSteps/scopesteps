"""Gemini adapter over the Interactions API (google-genai 2.x).

Policy enforced here, not left to SDK defaults:
- store=False: nothing is kept server-side; the harness owns state and replays model steps.
- No SDK retries (the SDK otherwise retries some failures invisibly).
- One model ID from configuration; no fallback model, provider or billing tier.
"""

import json
import re
import time
from collections.abc import Mapping
from typing import Any, Literal, cast

from google import genai
from google.genai import types as genai_types

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
from scopesteps.agent.domain.providers import FreeTierLimits, ProviderProfile

PROVIDER = "gemini"
PROFILE = ProviderProfile(
    name=PROVIDER,
    trace_name="gcp.gemini",
    api="gemini_interactions",
    default_model="gemini-3.5-flash-lite",
    free_tier=FreeTierLimits(
        requests_per_minute=15,
        tokens_per_minute=250_000,
        requests_per_day=500,
        tokens_per_day=None,
        checked="2026-10-12",
        source="AI Studio rate-limit page for this project (ADR 0004)",
    ),
    data_terms="Free tier may use prompts to improve Google products: synthetic data only.",
)
ThinkingLevel = Literal["minimal", "low", "medium", "high"]

_REPLAYED_STEP_TYPES = frozenset({"thought", "function_call", "model_output"})
_AUTH_REASONS = frozenset({"API_KEY_INVALID", "API_KEY_EXPIRED", "PERMISSION_DENIED"})
_RETRY_DELAY = re.compile(r"^(\d+(?:\.\d+)?)s$")

# attempts=0 does not disable retries (the SDK has two retry layers); attempts=1 plus a status
# list that never matches gives exactly one request (ADR 0004). test_gemini_http.py pins this
# against a local server so an SDK upgrade cannot undo it.
NO_RETRIES = genai_types.HttpRetryOptions(attempts=1, http_status_codes=[599])


class GeminiProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        timeout_seconds: float,
        thinking_level: ThinkingLevel,
        base_url: str | None = None,
    ) -> None:
        self._model_id = model_id
        self._timeout_seconds = timeout_seconds
        self._thinking_level: ThinkingLevel = thinking_level
        self._client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(
                base_url=base_url,
                timeout=int(timeout_seconds * 1000),
                retry_options=NO_RETRIES,
            ),
        )

    @property
    def model_id(self) -> str:
        return self._model_id

    def generate(self, request: ModelRequest) -> ModelResult:
        body = build_request_body(request, self._model_id, self._thinking_level)
        started = time.perf_counter()
        try:
            interaction = self._client.interactions.create(**body, timeout=self._timeout_seconds)
        except Exception as error:
            classified = classify_error(error)
            if classified is None:
                raise
            raise classified from error
        latency_ms = round((time.perf_counter() - started) * 1000)
        return parse_interaction(interaction, self._model_id, latency_ms)


def build_request_body(
    request: ModelRequest, model_id: str, thinking_level: ThinkingLevel
) -> dict[str, Any]:
    generation_config: dict[str, Any] = {
        "max_output_tokens": request.max_output_tokens,
        "thinking_level": thinking_level,
    }
    if request.tools:
        generation_config["tool_choice"] = (
            {"allowed_tools": {"mode": request.tool_choice, "tools": list(request.allowed_tools)}}
            if request.allowed_tools
            else request.tool_choice
        )
    body: dict[str, Any] = {
        "model": model_id,
        "store": False,
        "system_instruction": request.system_instruction,
        "input": [step for turn in request.history for step in _turn_to_steps(turn)],
        "generation_config": generation_config,
    }
    if request.tools:
        body["tools"] = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": dict(tool.parameters),
            }
            for tool in request.tools
        ]
    if request.output_schema is not None:
        body["response_format"] = {
            "type": "text",
            "mime_type": "application/json",
            "schema": _without_max_items(request.output_schema),
        }
    return body


def _without_max_items(node: Any) -> Any:
    """The schema without `maxItems`. Gemini counts it toward a schema-complexity limit and
    rejects the draft and change-set schemas with a bare HTTP 400 while it is there; validation
    and the code that stores a draft still enforce every limit."""
    if isinstance(node, Mapping):
        mapping = cast(Mapping[str, Any], node)
        return {
            key: _without_max_items(value) for key, value in mapping.items() if key != "maxItems"
        }
    if isinstance(node, list):
        return [_without_max_items(value) for value in cast(list[Any], node)]
    return node


def _turn_to_steps(turn: Turn) -> list[dict[str, Any]]:
    match turn:
        case UserMessage(text=text):
            return [{"type": "user_input", "content": [{"type": "text", "text": text}]}]
        case ModelTurn(steps=steps):
            return [dict(step) for step in steps]
        case ToolResults(results=results):
            return [
                {
                    "type": "function_result",
                    "call_id": result.call_id,
                    "name": result.name,
                    "result": json.dumps(result.output),
                    "is_error": result.is_error,
                }
                for result in results
            ]


def parse_interaction(interaction: Any, model_id: str, latency_ms: int) -> ModelResult:
    status = str(getattr(interaction, "status", "") or "")
    raw_steps = [_dump(step) for step in cast(list[Any], getattr(interaction, "steps", None) or [])]
    replayed = tuple(step for step in raw_steps if step.get("type") in _REPLAYED_STEP_TYPES)

    if status == "failed":
        raise _failed_interaction_error(interaction)

    tool_calls = tuple(
        ToolCall(
            id=str(step["id"]),
            name=str(step["name"]),
            arguments=cast(JsonObject, step.get("arguments") or {}),
        )
        for step in replayed
        if step.get("type") == "function_call"
    )
    texts = [
        str(content["text"])
        for step in replayed
        if step.get("type") == "model_output"
        for content in cast(list[dict[str, Any]], step.get("content") or [])
        if content.get("type") == "text" and "text" in content
    ]
    return ModelResult(
        provider=PROVIDER,
        model_id=str(getattr(interaction, "model", None) or model_id),
        turn=ModelTurn(steps=replayed),
        text="".join(texts) if texts else None,
        tool_calls=tool_calls,
        finish_reason=_finish_reason(status, bool(tool_calls)),
        usage=_usage(getattr(interaction, "usage", None)),
        latency_ms=latency_ms,
        provider_status=status,
    )


def _dump(step: Any) -> dict[str, Any]:
    if isinstance(step, Mapping):
        return dict(cast(Mapping[str, Any], step))
    return cast(dict[str, Any], step.model_dump(mode="json", by_alias=True, exclude_none=True))


def _finish_reason(status: str, has_tool_calls: bool) -> FinishReason:
    if has_tool_calls or status == "requires_action":
        return "tool_calls"
    if status == "completed":
        return "completed"
    if status in {"incomplete", "budget_exceeded"}:
        return "max_tokens"
    return "other"


def _usage(usage: Any) -> Usage:
    if usage is None:
        return Usage()

    def count(name: str) -> int:
        return int(getattr(usage, name, None) or 0)

    return Usage(
        input_tokens=count("total_input_tokens"),
        output_tokens=count("total_output_tokens"),
        thinking_tokens=count("total_thought_tokens"),
        total_tokens=count("total_tokens"),
    )


def _failed_interaction_error(interaction: Any) -> ModelProviderError:
    errors = cast(list[Any], getattr(interaction, "errors", None) or [])
    messages = " ".join(str(getattr(error, "message", "") or "") for error in errors).lower()
    if "safety" in messages or "blocked" in messages:
        return ModelProviderError("blocked", "The provider blocked the response")
    return ModelProviderError("unavailable", "The provider reported a failed interaction")


def classify_error(error: BaseException) -> ModelProviderError | None:
    """Map SDK/transport failures to a kind. Unrelated exceptions return None and propagate.

    Messages are generic on purpose: provider error bodies can echo request content.
    """
    module = type(error).__module__
    if not module.startswith(("google.genai", "httpx")):
        return None
    status_code = getattr(error, "status_code", None)
    name = type(error).__name__
    if not isinstance(status_code, int):
        if "Timeout" in name:
            return ModelProviderError("timeout", "The model provider did not respond in time")
        if "Connection" in name:
            return ModelProviderError("unavailable", "Could not reach the model provider")
        if "ResponseValidation" in name:
            return ModelProviderError("malformed_response", "Unexpected provider response")
        return ModelProviderError("unavailable", f"Model provider error ({name})")

    body = _error_body(error)
    reasons = {str(detail.get("reason", "")) for detail in body.get("details", [])}
    google_status = str(body.get("status", ""))
    label = f"HTTP {status_code}{f' {google_status}' if google_status else ''}"
    if status_code == 429:
        return ModelProviderError(
            "quota",
            f"Model quota or rate limit reached ({label})",
            retry_after_seconds=_retry_after(error, body),
            status_code=status_code,
        )
    if status_code in {401, 403} or reasons & _AUTH_REASONS:
        return ModelProviderError(
            "auth", f"Model provider rejected the credentials ({label})", status_code=status_code
        )
    if status_code == 408:
        return ModelProviderError("timeout", f"Model request timed out ({label})", status_code=408)
    if status_code >= 500:
        return ModelProviderError(
            "unavailable", f"Model provider unavailable ({label})", status_code=status_code
        )
    return ModelProviderError(
        "invalid_request", f"Model provider rejected the request ({label})", status_code=status_code
    )


def _error_body(error: BaseException) -> dict[str, Any]:
    body: Any = getattr(error, "body", None)
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return {}
    if isinstance(body, list) and body:  # Google sometimes wraps the error in a list.
        body = cast(list[Any], body)[0]
    if isinstance(body, dict):
        inner = cast(dict[str, Any], body).get("error", body)
        if isinstance(inner, dict):
            return cast(dict[str, Any], inner)
    return {}


def _retry_after(error: BaseException, body: dict[str, Any]) -> float | None:
    for detail in body.get("details", []):
        match = _RETRY_DELAY.match(str(detail.get("retryDelay", "")))
        if match:
            return float(match.group(1))
    headers = getattr(getattr(error, "response", None), "headers", None)
    value = headers.get("retry-after") if headers is not None else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
