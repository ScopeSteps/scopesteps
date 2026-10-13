"""Estimated model cost. The free tier is not billed; estimates show what paid use would cost."""

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from scopesteps.agent.domain.model import Usage

PRICES_CHECKED = "2026-10-12"
PRICE_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing (Standard paid tier)"
_PER_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1M tokens. Thinking tokens are billed as output."""

    input_per_million: Decimal
    output_per_million: Decimal


PRICES: dict[str, ModelPrice] = {
    "gemini-3.5-flash-lite": ModelPrice(Decimal("0.30"), Decimal("2.50")),
    # Rises to $1.50 / $7.50 on 2027-01-01.
    "gemini-3.8-flash": ModelPrice(Decimal("0.75"), Decimal("3.75")),
    # Groq on-demand prices (https://console.groq.com/docs/models), checked 2026-10-13.
    "openai/gpt-oss-120b": ModelPrice(Decimal("0.15"), Decimal("0.60")),
    "openai/gpt-oss-20b": ModelPrice(Decimal("0.075"), Decimal("0.30")),
    "qwen/qwen3.8-27b": ModelPrice(Decimal("0.80"), Decimal("4.00")),
}


def estimate_cost_usd(model_id: str, usage: Usage) -> Decimal | None:
    """Cost at paid rates, or None when the model has no recorded price."""
    name = model_id.removeprefix("models/")
    matches = [key for key in PRICES if name == key or name.startswith(f"{key}-0")]
    if not matches:
        return None
    price = PRICES[max(matches, key=len)]
    billed_output = usage.output_tokens + usage.thinking_tokens
    cost = (
        usage.input_tokens * price.input_per_million + billed_output * price.output_per_million
    ) / _PER_MILLION
    return cost.quantize(Decimal("0.000001"))


def estimate_cost_microusd(model_id: str, usage: Usage) -> int | None:
    """The estimate in millionths of a dollar, rounded up so limits err towards stopping."""
    cost = estimate_cost_usd(model_id, usage)
    if cost is None:
        return None
    return int((cost * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
