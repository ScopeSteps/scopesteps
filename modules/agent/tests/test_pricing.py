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
    per_call = estimate_cost_microusd(
        "claude-haiku-5-5", Usage(input_tokens=60_000, output_tokens=8_000)
    )

    three = worst_case_call_cost_microusd(
        "claude-haiku-5-5", input_tokens=60_000, max_output_tokens=8_000, calls=3
    )

    assert per_call is not None
    assert three == 3 * per_call
    assert worst_case_call_cost_microusd("unknown", input_tokens=1, max_output_tokens=1) is None
