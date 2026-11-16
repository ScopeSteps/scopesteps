"""Estimated model cost at each provider's paid rates, from the price table below."""

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from scopesteps.agent.domain.model import Usage

PRICES_CHECKED = "2026-11-15"
PRICE_SOURCE = (
    "https://platform.claude.com/docs/en/about-claude/pricing (Claude, checked 2026-11-15); "
    "https://ai.google.dev/gemini-api/docs/pricing (Gemini Standard paid tier, checked "
    "2026-10-12); https://console.groq.com/docs/models (Groq, checked 2026-10-13)"
)
_PER_MILLION = Decimal(1_000_000)
_MICROUSD = Decimal(1_000_000)


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1M tokens. Thinking tokens are billed as output. A cache price of None bills
    cached tokens as ordinary input, for models we send no cache breakpoints to."""

    input_per_million: Decimal
    output_per_million: Decimal
    cache_write_per_million: Decimal | None = None
    cache_read_per_million: Decimal | None = None
    long_prompt_tokens: int | None = None
    """Above this many input tokens in one prompt (cached or not), every rate is multiplied by
    `long_prompt_multiplier`."""
    long_prompt_multiplier: Decimal = Decimal(1)


PRICES: dict[str, ModelPrice] = {
    "claude-sonnet-5-5": ModelPrice(
        Decimal("2.00"), Decimal("10.00"), Decimal("2.50"), Decimal("0.10")
    ),
    "claude-haiku-5-5": ModelPrice(
        Decimal("0.10"),
        Decimal("0.50"),
        Decimal("0.125"),
        Decimal("0.01"),
        long_prompt_tokens=100_000,
        long_prompt_multiplier=Decimal(5),
    ),
    "gemini-3.5-flash-lite": ModelPrice(Decimal("0.30"), Decimal("2.50")),
    # Rises to $1.50 / $7.50 on 2027-01-01.
    "gemini-3.8-flash": ModelPrice(Decimal("0.75"), Decimal("3.75")),
    "openai/gpt-oss-120b": ModelPrice(Decimal("0.15"), Decimal("0.60")),
    "openai/gpt-oss-20b": ModelPrice(Decimal("0.075"), Decimal("0.30")),
    "qwen/qwen3.8-27b": ModelPrice(Decimal("0.80"), Decimal("4.00")),
}


def price_of(model_id: str) -> ModelPrice | None:
    name = model_id.removeprefix("models/")
    matches = [key for key in PRICES if name == key or name.startswith(f"{key}-0")]
    return PRICES[max(matches, key=len)] if matches else None


def estimate_cost_usd(model_id: str, usage: Usage) -> Decimal | None:
    """Cost of one call at paid rates, or None when the model has no recorded price."""
    price = price_of(model_id)
    if price is None:
        return None
    prompt_tokens = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    long = price.long_prompt_tokens is not None and prompt_tokens > price.long_prompt_tokens
    multiplier = price.long_prompt_multiplier if long else Decimal(1)
    write = price.cache_write_per_million or price.input_per_million
    read = price.cache_read_per_million or price.input_per_million
    billed_output = usage.output_tokens + usage.thinking_tokens
    cost = (
        usage.input_tokens * price.input_per_million
        + usage.cache_write_tokens * write
        + usage.cache_read_tokens * read
        + billed_output * price.output_per_million
    ) * multiplier
    return (cost / _PER_MILLION).quantize(Decimal("0.000001"))


def estimate_cost_microusd(model_id: str, usage: Usage) -> int | None:
    """The estimate in millionths of a dollar, rounded up so limits err towards stopping."""
    cost = estimate_cost_usd(model_id, usage)
    if cost is None:
        return None
    return int((cost * _MICROUSD).to_integral_value(rounding=ROUND_CEILING))


def worst_case_call_cost_microusd(
    model_id: str, *, input_tokens: int, max_output_tokens: int, calls: int = 1
) -> int | None:
    """What `calls` calls could cost before they are made, never less than they will: all input
    at the cache-write rate, the highest input rate (a call can write its whole prompt to the
    cache), and every call using its whole output allowance. The allowance covers thinking too,
    so expected thinking is counted as output. The long-prompt rate is decided per call, as the
    provider decides it per prompt, and multiplies the cache-write rate too. None when the model
    has no price."""
    one = estimate_cost_microusd(
        model_id, Usage(cache_write_tokens=input_tokens, output_tokens=max_output_tokens)
    )
    return None if one is None else one * calls
