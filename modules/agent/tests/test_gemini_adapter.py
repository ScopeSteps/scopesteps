import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelTurn,
    ToolResult,
    ToolResults,
    ToolSpec,
    UserMessage,
)
from scopesteps.agent.infrastructure.providers.gemini import (
    build_request_body,
    classify_error,
    parse_interaction,
)

TOOL = ToolSpec(name="lookup_source", description="Search sources", parameters={"type": "object"})
SCHEMA = {"type": "object", "properties": {"greeting": {"type": "string"}}}
THOUGHT = {"type": "thought", "signature": "c2lnbmF0dXJl"}
CALL = {
    "type": "function_call",
    "id": "call-1",
    "name": "lookup_source",
    "arguments": {"query": "cancel"},
}


BASE_REQUEST = ModelRequest(
    system_instruction="Policy", history=(UserMessage("Sources"),), max_output_tokens=500
)


def _request(**overrides: Any) -> ModelRequest:
    return replace(BASE_REQUEST, **overrides)


def test_requests_are_stateless_and_configured_explicitly() -> None:
    body = build_request_body(_request(), "gemini-x", "low")

    assert body["store"] is False
    assert body["model"] == "gemini-x"
    assert body["generation_config"] == {"max_output_tokens": 500, "thinking_level": "low"}
    assert body["input"] == [
        {"type": "user_input", "content": [{"type": "text", "text": "Sources"}]}
    ]
    assert "tools" not in body
    assert "response_format" not in body


@pytest.mark.parametrize(
    ("overrides", "tool_choice"),
    [
        ({"tools": (TOOL,)}, "auto"),
        ({"tools": (TOOL,), "tool_choice": "none"}, "none"),
        (
            {"tools": (TOOL,), "tool_choice": "any", "allowed_tools": ("lookup_source",)},
            {"allowed_tools": {"mode": "any", "tools": ["lookup_source"]}},
        ),
    ],
)
def test_tool_choice_is_passed_through(overrides: dict[str, Any], tool_choice: object) -> None:
    body = build_request_body(_request(**overrides), "m", "low")

    assert body["generation_config"]["tool_choice"] == tool_choice
    assert body["tools"][0]["type"] == "function"
    assert body["tools"][0]["name"] == "lookup_source"


def test_output_schema_becomes_json_response_format() -> None:
    body = build_request_body(_request(output_schema=SCHEMA), "m", "low")

    assert body["response_format"] == {
        "type": "text",
        "mime_type": "application/json",
        "schema": SCHEMA,
    }


def test_model_steps_are_replayed_verbatim_with_tool_results() -> None:
    history = (
        UserMessage("Sources"),
        ModelTurn(steps=(THOUGHT, CALL)),
        ToolResults((ToolResult(call_id="call-1", name="lookup_source", output={"blocks": []}),)),
    )

    body = build_request_body(_request(history=history), "m", "low")

    assert body["input"][1:] == [
        THOUGHT,
        CALL,
        {
            "type": "function_result",
            "call_id": "call-1",
            "name": "lookup_source",
            "result": json.dumps({"blocks": []}),
            "is_error": False,
        },
    ]


def _interaction(status: str, steps: list[dict[str, Any]], **usage: int) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        model="gemini-x-001",
        steps=[{"type": "user_input", "content": []}, *steps],
        usage=SimpleNamespace(**usage) if usage else None,
        errors=None,
    )


def test_tool_calls_usage_and_replay_steps_are_parsed() -> None:
    interaction = _interaction(
        "requires_action",
        [THOUGHT, CALL],
        total_input_tokens=10,
        total_output_tokens=5,
        total_thought_tokens=2,
        total_tokens=17,
    )

    result = parse_interaction(interaction, "gemini-x", latency_ms=42)

    assert result.finish_reason == "tool_calls"
    assert [(c.id, c.name, dict(c.arguments)) for c in result.tool_calls] == [
        ("call-1", "lookup_source", {"query": "cancel"})
    ]
    assert result.turn.steps == (THOUGHT, CALL)
    assert (result.usage.input_tokens, result.usage.thinking_tokens, result.usage.total_tokens) == (
        10,
        2,
        17,
    )
    assert result.model_id == "gemini-x-001"


@pytest.mark.parametrize(
    ("status", "finish_reason"),
    [
        ("completed", "completed"),
        ("incomplete", "max_tokens"),
        ("budget_exceeded", "max_tokens"),
        ("cancelled", "other"),
    ],
)
def test_status_maps_to_finish_reason(status: str, finish_reason: str) -> None:
    output = {
        "type": "model_output",
        "content": [{"type": "text", "text": '{"a":'}, {"type": "text", "text": "1}"}],
    }

    result = parse_interaction(_interaction(status, [output]), "m", 1)

    assert result.finish_reason == finish_reason
    assert result.text == '{"a":1}'


@pytest.mark.parametrize(
    ("message", "kind"),
    [("Response blocked for safety", "blocked"), ("Internal problem", "unavailable")],
)
def test_failed_interactions_raise_classified_errors(message: str, kind: str) -> None:
    interaction = _interaction("failed", [])
    interaction.errors = [SimpleNamespace(message=message)]

    with pytest.raises(ModelProviderError) as raised:
        parse_interaction(interaction, "m", 1)

    assert raised.value.kind == kind


def _sdk_error(name: str, status_code: int | None = None, body: object = None) -> Exception:
    error_type = type(name, (Exception,), {"__module__": "google.genai._gaos.lib.compat_errors"})
    error = error_type("boom")
    setattr(error, "status_code", status_code)  # noqa: B010
    setattr(error, "body", body)  # noqa: B010
    return error


API_KEY_INVALID = [
    {"error": {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}
]
QUOTA = {"error": {"status": "RESOURCE_EXHAUSTED", "details": [{"retryDelay": "17s"}]}}


@pytest.mark.parametrize(
    ("error", "kind", "retryable"),
    [
        (_sdk_error("RateLimitError", 429, QUOTA), "quota", True),
        (_sdk_error("BadRequestError", 400, API_KEY_INVALID), "auth", False),
        (_sdk_error("AuthenticationError", 401), "auth", False),
        (_sdk_error("PermissionDeniedError", 403), "auth", False),
        (
            _sdk_error("BadRequestError", 400, '{"error": {"code": "invalid_request"}}'),
            "invalid_request",
            False,
        ),
        (_sdk_error("InternalServerError", 503), "unavailable", True),
        (_sdk_error("APIStatusError", 408), "timeout", True),
        (_sdk_error("APITimeoutError"), "timeout", True),
        (_sdk_error("APIConnectionError"), "unavailable", True),
        (_sdk_error("APIResponseValidationError"), "malformed_response", False),
    ],
)
def test_sdk_errors_are_classified(error: Exception, kind: str, retryable: bool) -> None:
    classified = classify_error(error)

    assert classified is not None
    assert (classified.kind, classified.retryable) == (kind, retryable)


def test_quota_errors_carry_the_retry_delay() -> None:
    classified = classify_error(_sdk_error("RateLimitError", 429, QUOTA))

    assert classified is not None
    assert classified.retry_after_seconds == 17


def test_error_messages_never_include_provider_bodies() -> None:
    body = {"error": {"message": "echoed SECRET source text", "status": "INVALID_ARGUMENT"}}

    classified = classify_error(_sdk_error("BadRequestError", 400, body))

    assert classified is not None
    assert "SECRET" not in classified.message


def test_unrelated_exceptions_are_not_classified() -> None:
    assert classify_error(KeyError("bug in our code")) is None
