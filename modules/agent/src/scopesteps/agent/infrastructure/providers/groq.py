"""Groq: the backup provider (ADR 0006), reached through the OpenAI-compatible adapter."""

from scopesteps.agent.domain.providers import FreeTierLimits, ProviderProfile

PROFILE = ProviderProfile(
    name="groq",
    trace_name="groq",
    api="openai_chat_completions",
    default_model="openai/gpt-oss-120b",
    base_url="https://api.groq.com/openai/v1",
    free_tier=FreeTierLimits(
        requests_per_minute=30,
        tokens_per_minute=8_000,
        requests_per_day=1_000,
        tokens_per_day=200_000,
        checked="2026-10-13",
        source="https://console.groq.com/docs/rate-limits and the console metrics page",
    ),
    # 8K tokens a minute: a draft prompt (about 2.5K) plus this ceiling stays inside it.
    max_output_tokens_cap=6_000,
    reasoning_effort_models=("openai/gpt-oss",),
    # Reported input tokens for v3 drafts were 3.9-4.0 characters each (2026-10-14, 9 calls); 3.5
    # keeps a margin while giving the output about 600 more tokens than the generic estimate.
    request_chars_per_token=3.5,
    data_terms="Check Groq's terms for API data retention: synthetic data only on the free tier.",
)
