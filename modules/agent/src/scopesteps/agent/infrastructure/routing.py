"""One adapter per provider, each traced, and the model each step of a run calls (ADR 0032)."""

from collections.abc import Callable, Mapping

from scopesteps.agent.application.ports import ModelProvider, StepModel
from scopesteps.agent.domain.profiles import ModelNotServedError, Step, StepBinding
from scopesteps.agent.infrastructure.providers.anthropic import CATALOG as ANTHROPIC_CATALOG
from scopesteps.agent.infrastructure.providers.traced import TracedProvider, TraceSink, log_sink

RequestLimit = Callable[[StepBinding], int | None]
"""What one request to a binding's model may hold, or None when not known."""


def _no_limit(_: StepBinding) -> int | None:
    return None


_CATALOGS = {ANTHROPIC_CATALOG.name: ANTHROPIC_CATALOG}


def catalog_request_limit(binding: StepBinding) -> int | None:
    """A binding's model's input limit from its provider's catalog; None for a model no catalog
    lists (fake, replay), which then has no limit beyond the run's own."""
    catalog = _CATALOGS.get(binding.provider)
    capabilities = catalog.capabilities(binding.model) if catalog else None
    return capabilities.max_input_tokens if capabilities else None


class ModelRouter:
    """Serves the providers it was given and nothing else; there is no fallback provider."""

    def __init__(
        self,
        adapters: Mapping[str, ModelProvider],
        *,
        trace_sink: TraceSink = log_sink,
        request_limit: RequestLimit = _no_limit,
    ) -> None:
        self._adapters: dict[str, ModelProvider] = {
            name: TracedProvider(adapter, provider_name=name, sink=trace_sink)
            for name, adapter in adapters.items()
        }
        self._request_limit = request_limit

    @property
    def providers(self) -> frozenset[str]:
        return frozenset(self._adapters)

    def serves(self, bindings: Mapping[Step, StepBinding]) -> bool:
        return all(binding.provider in self._adapters for binding in bindings.values())

    def route(self, bindings: Mapping[Step, StepBinding], step: Step) -> StepModel:
        binding = bindings[step]
        adapter = self._adapters.get(binding.provider)
        if adapter is None:
            raise ModelNotServedError(
                f"This run uses {binding.provider} {binding.model} for {step.value}, which the "
                "API no longer serves. Configure it again or start a new run."
            )
        return StepModel(step, binding, adapter, self._request_limit(binding))
