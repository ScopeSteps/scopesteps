"""Run limits, checked before every model call. Resuming a run never resets the counters."""

import math
from dataclasses import dataclass, replace

from scopesteps.agent.domain.model import ModelResult
from scopesteps.kernel import DomainError

# Deliberately pessimistic (about 3 characters per token) so the pre-call check errs towards
# stopping. Real usage reported by the provider replaces the estimate after each call.
CHARS_PER_TOKEN_ESTIMATE = 3


class BudgetExceededError(DomainError):
    code = "RUN_BUDGET_EXCEEDED"


@dataclass(frozen=True)
class RunLimits:
    max_turns: int
    max_tool_calls: int
    max_output_tokens_per_call: int
    max_total_tokens: int


@dataclass(frozen=True)
class RunCounters:
    model_turns: int = 0
    tool_calls: int = 0
    total_tokens: int = 0

    def after_call(self, result: ModelResult) -> RunCounters:
        return replace(
            self,
            model_turns=self.model_turns + 1,
            tool_calls=self.tool_calls + len(result.tool_calls),
            total_tokens=self.total_tokens + result.usage.total_tokens,
        )

    def after_failed_call(self) -> RunCounters:
        """A failed or timed-out call still counts: the provider may have done (and billed) work."""
        return replace(self, model_turns=self.model_turns + 1)


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN_ESTIMATE)


def check_can_call(counters: RunCounters, limits: RunLimits, estimated_input_tokens: int) -> None:
    """Refuse a call that could push the run past a limit, before anything is sent."""
    if counters.model_turns >= limits.max_turns:
        raise BudgetExceededError(
            f"Run reached its limit of {limits.max_turns} model turns",
            details={"limit": "max_turns"},
        )
    if counters.tool_calls >= limits.max_tool_calls:
        raise BudgetExceededError(
            f"Run reached its limit of {limits.max_tool_calls} tool calls",
            details={"limit": "max_tool_calls"},
        )
    worst_case = counters.total_tokens + estimated_input_tokens + limits.max_output_tokens_per_call
    if worst_case > limits.max_total_tokens:
        raise BudgetExceededError(
            f"Next call could use up to {worst_case} tokens; the run limit is "
            f"{limits.max_total_tokens}",
            details={"limit": "max_total_tokens"},
        )
