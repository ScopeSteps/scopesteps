from decimal import Decimal

import pytest

from scopesteps.agent.domain.model import Usage
from scopesteps.agent.domain.pricing import (
    estimate_cost_microusd,
    estimate_cost_usd,
    worst_case_call_cost_microusd,
)

MILLION = 1_000_000


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        (Usage(input_tokens=MILLION), Decimal("2.000000")),
        (Usage(output_tokens=MILLION), Decimal("10.000000")),
        (Usage(thinking_tokens=MILLION), Decimal("10.000000")),
        (Usage(cache_write_tokens=MILLION), Decimal("2.500000")),
        (Usage(cache_read_tokens=MILLION), Decimal("0.100000")),
    ],
)
def test_sonnet_prices_each_kind_of_token(usage: Usage, expected: Decimal) -> None:
    assert estimate_cost_usd("claude-sonnet-5-5", usage) == expected


def test_haiku_costs_five_times_as_much_above_100k_prompt_tokens() -> None:
    short = Usage(input_tokens=60_000, cache_read_tokens=40_000, output_tokens=10_000)
    long = Usage(input_tokens=60_000, cache_read_tokens=40_001, output_tokens=10_000)

    short_cost = estimate_cost_usd("claude-haiku-5-5", short)
    long_cost = estimate_cost_usd("claude-haiku-5-5", long)

    assert short_cost == Decimal("0.011400")
    assert long_cost == Decimal("0.057000")


def test_worst_case_bills_the_whole_output_allowance_and_decides_the_long_rate_per_call() -> None:
    # 60K prompt tokens at Haiku's $0.125 cache-write rate plus 8K output at $0.50: $0.0115.
    three = worst_case_call_cost_microusd(
        "claude-haiku-5-5", input_tokens=60_000, max_output_tokens=8_000, calls=3
    )

    assert three == 3 * 11_500
    assert worst_case_call_cost_microusd("unknown", input_tokens=1, max_output_tokens=1) is None


def test_worst_case_applies_haikus_long_prompt_rate_on_top_of_the_cache_write_rate() -> None:
    # 120K tokens at $0.125 plus 8K at $0.50 is $0.019; above 100K every rate is 5x.
    cost = worst_case_call_cost_microusd(
        "claude-haiku-5-5", input_tokens=120_000, max_output_tokens=8_000
    )

    assert cost == 5 * 19_000


@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-haiku-5-5"])
@pytest.mark.parametrize("prompt", [60_000, 100_000, 100_001, 400_000])
@pytest.mark.parametrize("written", [0.0, 0.5, 1.0])
def test_worst_case_is_never_below_what_the_call_can_cost(
    model: str, prompt: int, written: float
) -> None:
    write = int(prompt * written)
    actual = estimate_cost_microusd(
        model, Usage(input_tokens=prompt - write, cache_write_tokens=write, output_tokens=8_000)
    )

    worst = worst_case_call_cost_microusd(model, input_tokens=prompt, max_output_tokens=8_000)

    assert actual is not None
    assert worst is not None
    assert worst >= actual
