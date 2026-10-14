import json
import time
from collections.abc import Callable

from scopesteps.agent.application.ports import ModelProvider
from scopesteps.agent.domain.budget import estimate_tokens
from scopesteps.agent.domain.model import ModelRequest, ModelResult, UserMessage
from scopesteps.agent.domain.rate import TokenWindow

# Expected output before any call has reported one; later calls use the running average.
_FIRST_OUTPUT_GUESS = 2000


class PacedProvider:
    """Waits before a call that would exceed the provider's tokens-per-minute allowance.

    For batch tools (probe, evaluations) that can afford to wait. Request-driven runs do not use
    it: a step must finish within its lease, so a 429 there is returned as a retryable error.
    """

    def __init__(
        self,
        inner: ModelProvider,
        window: TokenWindow,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        log: Callable[[str], None] = print,
    ) -> None:
        self._inner = inner
        self._window = window
        self._clock = clock
        self._sleep = sleep
        self._log = log
        self._outputs: list[int] = []

    def generate(self, request: ModelRequest) -> ModelResult:
        expected_output = (
            sum(self._outputs) // len(self._outputs) if self._outputs else _FIRST_OUTPUT_GUESS
        )
        upcoming = _estimated_input(request) + min(expected_output, request.max_output_tokens)
        wait = self._window.wait_seconds(self._clock(), upcoming)
        if wait > 0:
            self._log(f"  pacing for the per-minute token limit: waiting {wait:.0f}s")
            self._sleep(wait)
        result = self._inner.generate(request)
        if not result.usage_reported:
            # The provider still counts the rejected generation against the minute, so charge
            # the worst case and keep it out of the output average.
            output = result.output_budget or request.max_output_tokens
            worst_case = _estimated_input(request) + output
            self._window.record(self._clock(), worst_case)
            return result
        self._window.record(self._clock(), result.usage.total_tokens)
        self._outputs.append(result.usage.output_tokens + result.usage.thinking_tokens)
        return result


def _estimated_input(request: ModelRequest) -> int:
    parts = [request.system_instruction]
    for turn in request.history:
        parts.append(turn.text if isinstance(turn, UserMessage) else json.dumps(turn, default=str))
    return estimate_tokens("".join(parts))
