"""What we know about Anthropic's models (ADR 0032). The adapter is in `anthropic_messages.py`."""

from scopesteps.agent.domain.providers import ModelCapabilities, ModelCatalog

PROVIDER = "anthropic"
CATALOG = ModelCatalog(
    name=PROVIDER,
    trace_name="anthropic",
    api="anthropic_messages",
    models={
        # Forced tool choice (`any` or a named tool) is refused with a 400 on Sonnet 5.5.
        "claude-sonnet-5-5": ModelCapabilities(
            max_input_tokens=1_000_000,
            max_output_tokens=128_000,
            supports_forced_tool_choice=False,
        ),
        "claude-haiku-5-5": ModelCapabilities(
            max_input_tokens=1_000_000,
            max_output_tokens=128_000,
            supports_forced_tool_choice=True,
        ),
    },
    checked="2026-11-15",
    source="https://platform.claude.com/docs/en/about-claude/models/overview",
    data_terms=(
        "Paid API: inputs and outputs are not used for training by default and are deleted "
        "within 30 days. Synthetic or de-identified data only, as everywhere in this repository."
    ),
)
