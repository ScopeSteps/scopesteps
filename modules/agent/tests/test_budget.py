from dataclasses import replace

import pytest

from scopesteps.agent.domain.budget import (
    BudgetExceededError,
    RunCounters,
    RunInputTooLargeError,
    RunLimits,
    check_can_call,
    check_request_fits,
    estimate_tokens,
)
from scopesteps.agent.domain.model import ModelResult, ModelTurn, ToolCall, Usage
from scopesteps.agent.infrastructure.providers import gemini, groq

LIMITS = RunLimits(
    max_turns=6, max_tool_calls=8, max_output_tokens_per_call=1000, max_total_tokens=10_000
)


def _result(total_tokens: int, tool_calls: int = 0) -> ModelResult:
    return ModelResult(
        provider="test",
        model_id="m",
        turn=ModelTurn(steps=()),
        text=None,
        tool_calls=tuple(ToolCall(id=str(i), name="t", arguments={}) for i in range(tool_calls)),
        finish_reason="completed",
        usage=Usage(total_tokens=total_tokens),
        latency_ms=1,
    )


@pytest.mark.parametrize(
    ("counters", "estimated_input", "limit"),
    [
        (RunCounters(model_turns=6), 0, "max_turns"),
        (RunCounters(tool_calls=8), 0, "max_tool_calls"),
        (RunCounters(total_tokens=8_500), 600, "max_total_tokens"),
    ],
)
def test_calls_past_a_limit_are_refused(
    counters: RunCounters, estimated_input: int, limit: str
) -> None:
    with pytest.raises(BudgetExceededError) as raised:
        check_can_call(counters, LIMITS, estimated_input)

    assert raised.value.details["limit"] == limit


def test_call_within_limits_is_allowed() -> None:
    check_can_call(RunCounters(model_turns=5, tool_calls=7, total_tokens=8_000), LIMITS, 1_000)


def test_counters_accumulate_reported_usage_and_tool_calls() -> None:
    counters = RunCounters().after_call(_result(1_500, tool_calls=2)).after_call(_result(500))

    assert counters == RunCounters(model_turns=2, tool_calls=2, total_tokens=2_000)


def test_failed_calls_still_use_a_turn() -> None:
    assert RunCounters().after_failed_call() == RunCounters(model_turns=1)


def test_token_estimate_is_pessimistic() -> None:
    assert estimate_tokens("a" * 300) == 100
    assert estimate_tokens("") == 0


def test_a_request_must_leave_room_for_the_output_within_the_model_limit() -> None:
    limits = RunLimits(
        max_turns=6, max_tool_calls=8, max_output_tokens_per_call=8_000, max_total_tokens=600_000
    )

    check_request_fits(92_000, limits, max_request_tokens=100_000)
    check_request_fits(10**9, limits, max_request_tokens=None)
    with pytest.raises(RunInputTooLargeError) as refused:
        check_request_fits(92_001, limits, max_request_tokens=100_000)

    assert refused.value.code == "RUN_INPUT_TOO_LARGE"
    assert refused.value.details["limit"] == "max_request_tokens"
    # 92,001 tokens of about 3 characters at about 6 characters a word.
    assert "about 46,000 words with the instructions" in refused.value.message
    assert "it reads about 46,000" in refused.value.message


def test_a_request_is_limited_by_the_model_or_the_per_minute_allowance_whichever_is_lower() -> None:
    profile = replace(gemini.PROFILE, max_input_tokens=1_048_576)

    assert profile.request_token_limit(None) == 1_048_576
    assert profile.request_token_limit(250_000) == 250_000
    assert replace(profile, max_input_tokens=None).request_token_limit(None) is None
    assert groq.PROFILE.request_token_limit(8_000) == 8_000
