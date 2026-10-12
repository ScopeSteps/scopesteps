from typing import Protocol

from scopesteps.agent.domain.model import ModelRequest, ModelResult


class ModelProvider(Protocol):
    """The only way agent code reaches a model.

    One configured provider per process. Implementations never retry, fall back to another model
    or provider, or switch billing tiers; they raise ModelProviderError and the caller decides.
    """

    def generate(self, request: ModelRequest) -> ModelResult: ...
