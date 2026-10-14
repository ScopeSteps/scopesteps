import json
import logging
import time
from collections.abc import Callable
from typing import Any

from scopesteps.agent.application.ports import ModelProvider
from scopesteps.agent.application.tracing import current_attributes
from scopesteps.agent.domain.model import ModelProviderError, ModelRequest, ModelResult
from scopesteps.agent.domain.pricing import estimate_cost_usd

TraceSink = Callable[[dict[str, Any]], None]
_logger = logging.getLogger("scopesteps.agent.model_calls")


def log_sink(event: dict[str, Any]) -> None:
    _logger.info(json.dumps(event, sort_keys=True))


class TracedProvider:
    """Emits one content-free event per model call, success or failure, then passes through."""

    def __init__(
        self, inner: ModelProvider, *, provider_name: str, model_id: str, sink: TraceSink
    ) -> None:
        self._inner = inner
        self._provider_name = provider_name
        self._model_id = model_id
        self._sink = sink

    def generate(self, request: ModelRequest) -> ModelResult:
        event: dict[str, Any] = {
            "name": "gen_ai.chat",
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": self._provider_name,
            "gen_ai.request.model": self._model_id,
            "gen_ai.request.max_tokens": request.max_output_tokens,
            "scopesteps.structured_output": request.output_schema is not None,
            "scopesteps.tools_offered": len(request.tools),
            "scopesteps.history_turns": len(request.history),
            **current_attributes(),
        }
        started = time.perf_counter()
        try:
            result = self._inner.generate(request)
        except ModelProviderError as error:
            event |= {
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "error.type": error.kind,
                "scopesteps.retryable": error.retryable,
            }
            self._sink(event)
            raise
        cost = estimate_cost_usd(result.model_id, result.usage)
        if result.output_budget is not None:
            # The adapter lowered the limit to fit the provider's cap; record what was sent.
            event["gen_ai.request.max_tokens"] = result.output_budget
        event |= {
            "duration_ms": result.latency_ms,
            "gen_ai.response.model": result.model_id,
            "gen_ai.response.finish_reasons": [result.finish_reason],
            "gen_ai.usage.input_tokens": result.usage.input_tokens,
            "gen_ai.usage.output_tokens": result.usage.output_tokens,
            "scopesteps.usage.thinking_tokens": result.usage.thinking_tokens,
            "scopesteps.tool_calls": len(result.tool_calls),
            "scopesteps.cost_usd_estimate": str(cost) if cost is not None else None,
        }
        self._sink(event)
        return result
