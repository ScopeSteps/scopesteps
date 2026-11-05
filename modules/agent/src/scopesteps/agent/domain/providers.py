"""What we know about each model provider, kept in one place per provider (`infrastructure/
providers/<name>.py`). Adapters are per API style; profiles hold per-provider defaults, limits and
quirks, so code never branches on a provider name."""

from dataclasses import dataclass

REPLAY_PROVIDER = "replay"
"""The provider a run is pinned to when it answers from a recording (ADR 0018)."""


@dataclass(frozen=True)
class FreeTierLimits:
    """Published free-tier limits for the default model, as checked on `checked`."""

    requests_per_minute: int
    tokens_per_minute: int | None
    requests_per_day: int | None
    tokens_per_day: int | None
    checked: str
    source: str


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    trace_name: str
    """`gen_ai.provider.name` in traces (OpenTelemetry GenAI conventions)."""
    api: str
    """Which adapter speaks to it: `gemini_interactions` or `openai_chat_completions`."""
    default_model: str
    free_tier: FreeTierLimits
    base_url: str | None = None
    max_output_tokens_cap: int | None = None
    """Lower ceiling for one call's output, so one call fits the per-minute token allowance."""
    reasoning_effort_models: tuple[str, ...] = ()
    """Model id prefixes that accept `reasoning_effort` (OpenAI-compatible APIs only)."""
    request_chars_per_token: float | None = None
    """Measured characters per input token, used to fit a request inside a per-request token limit.
    None keeps the generic pessimistic estimate, which can leave too little room for the output."""
    max_input_tokens: int | None = None
    """The default model's published limit on one request: input, thinking and output together."""
    data_terms: str = ""

    def request_token_limit(self, tokens_per_minute: int | None) -> int | None:
        """What one request may hold: the model's limit, or the per-minute allowance when that is
        lower, since a request larger than a minute's allowance can never be sent."""
        limits = [limit for limit in (self.max_input_tokens, tokens_per_minute) if limit]
        return min(limits) if limits else None
