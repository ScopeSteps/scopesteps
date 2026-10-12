import json
from decimal import Decimal
from typing import Any

import pytest

from scopesteps.agent.application.tracing import current_attributes, trace_scope
from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    Usage,
    UserMessage,
)
from scopesteps.agent.domain.pricing import estimate_cost_usd
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.agent.infrastructure.providers.traced import TracedProvider

PRIVATE_SOURCE = "CONFIDENTIAL source sentence"
REQUEST = ModelRequest(
    system_instruction="policy text", history=(UserMessage(PRIVATE_SOURCE),), max_output_tokens=50
)
RESULT = ModelResult(
    provider="gemini",
    model_id="gemini-3.5-flash-lite",
    turn=ModelTurn(({"type": "model_output", "text": "MODEL OUTPUT"},)),
    text="MODEL OUTPUT",
    tool_calls=(),
    finish_reason="completed",
    usage=Usage(input_tokens=1_000_000, output_tokens=100_000, thinking_tokens=100_000),
    latency_ms=42,
)


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("gemini-3.5-flash-lite", Decimal("0.800000")),
        ("models/gemini-3.5-flash-lite-001", Decimal("0.800000")),
        ("gemini-3.8-flash", Decimal("1.500000")),
        ("gemini-unknown", None),
    ],
)
def test_cost_estimates_bill_thinking_as_output(model_id: str, expected: Decimal | None) -> None:
    assert estimate_cost_usd(model_id, RESULT.usage) == expected


def _traced(
    script: list[ModelResult | ModelProviderError],
) -> tuple[TracedProvider, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    provider = TracedProvider(
        ScriptedProvider(script),
        provider_name="gcp.gemini",
        model_id="gemini-3.5-flash-lite",
        sink=events.append,
    )
    return provider, events


def test_successful_calls_emit_one_content_free_event_with_scope_attributes() -> None:
    provider, events = _traced([RESULT])

    with trace_scope(run_id="r1", pack="campus"), trace_scope(attempt=2):
        provider.generate(REQUEST)

    (event,) = events
    assert event["gen_ai.provider.name"] == "gcp.gemini"
    assert event["gen_ai.request.model"] == "gemini-3.5-flash-lite"
    assert event["gen_ai.usage.input_tokens"] == 1_000_000
    assert event["scopesteps.usage.thinking_tokens"] == 100_000
    assert event["scopesteps.cost_usd_estimate"] == "0.800000"
    assert event["gen_ai.response.finish_reasons"] == ["completed"]
    assert (event["scopesteps.run_id"], event["scopesteps.pack"], event["scopesteps.attempt"]) == (
        "r1",
        "campus",
        2,
    )
    serialized = json.dumps(event)
    assert PRIVATE_SOURCE not in serialized
    assert "policy text" not in serialized
    assert "MODEL OUTPUT" not in serialized


def test_failed_calls_are_traced_and_still_raise() -> None:
    provider, events = _traced([ModelProviderError("quota", "limit")])

    with pytest.raises(ModelProviderError):
        provider.generate(REQUEST)

    assert events[0]["error.type"] == "quota"
    assert events[0]["scopesteps.retryable"] is True


def test_trace_scopes_nest_and_unwind() -> None:
    with trace_scope(run_id="r1"):
        with trace_scope(attempt=1):
            assert current_attributes() == {"scopesteps.run_id": "r1", "scopesteps.attempt": 1}
        assert current_attributes() == {"scopesteps.run_id": "r1"}
    assert current_attributes() == {}
