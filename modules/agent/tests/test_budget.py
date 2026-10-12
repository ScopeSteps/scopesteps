import pytest

from scopesteps.agent.domain.budget import (
    BudgetExceededError,
    RunCounters,
    RunLimits,
    check_can_call,
    estimate_tokens,
)
from scopesteps.agent.domain.model import ModelResult, ModelTurn, ToolCall, Usage

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
