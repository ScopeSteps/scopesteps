"""What we know about each model provider, kept in one place per provider (`infrastructure/
providers/<name>.py`): each model's limits and quirks, so code never branches on a model name."""

from collections.abc import Mapping
from dataclasses import dataclass

REPLAY_PROVIDER = "replay"
"""The provider a run is pinned to when it answers from a recording (ADR 0018)."""


@dataclass(frozen=True)
class ModelCapabilities:
    """What one model accepts, from the provider's model page, as checked on its catalog's date."""

    max_input_tokens: int
    """The model's limit on one request's input."""
    max_output_tokens: int
    supports_forced_tool_choice: bool
    """Whether the model accepts a tool choice that forces a tool call. Without it the adapter
    asks for a tool call in the prompt, and an answer with no tool call is bad output."""


@dataclass(frozen=True)
class ModelCatalog:
    """A paid provider whose adapter serves several models, each step choosing one (ADR 0032)."""

    name: str
    trace_name: str
    """`gen_ai.provider.name` in traces (OpenTelemetry GenAI conventions)."""
    api: str
    models: Mapping[str, ModelCapabilities]
    checked: str
    source: str
    data_terms: str = ""

    def capabilities(self, model: str) -> ModelCapabilities | None:
        return self.models.get(model)
