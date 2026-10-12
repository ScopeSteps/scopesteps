from collections.abc import Iterable

from scopesteps.agent.domain.model import ModelProviderError, ModelRequest, ModelResult


class ScriptedProvider:
    """Replays prepared results or errors in order and records every request. For tests and CI."""

    def __init__(self, script: Iterable[ModelResult | ModelProviderError]) -> None:
        self._script = list(script)
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        if not self._script:
            raise AssertionError("ScriptedProvider has no more scripted results")
        step = self._script.pop(0)
        if isinstance(step, ModelProviderError):
            raise step
        return step
