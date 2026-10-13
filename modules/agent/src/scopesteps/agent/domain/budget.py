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
    max_cost_microusd: int | None = None
    """Estimated cost limit for the run at paid rates; None for no limit."""


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


def check_can_call(
    counters: RunCounters, limits: RunLimits, estimated_input_tokens: int, *, calls: int = 1
) -> None:
    """Refuse a step that could push the run past a limit, before anything is sent.

    `calls` reserves room for a step that may make several calls, such as a draft and its repair.
    """
    if counters.model_turns + calls > limits.max_turns:
        raise BudgetExceededError(
            f"Run reached its limit of {limits.max_turns} model turns",
            details={"limit": "max_turns"},
        )
    if counters.tool_calls >= limits.max_tool_calls:
        raise BudgetExceededError(
            f"Run reached its limit of {limits.max_tool_calls} tool calls",
            details={"limit": "max_tool_calls"},
        )
    worst_case = counters.total_tokens + calls * (
        estimated_input_tokens + limits.max_output_tokens_per_call
    )
    if worst_case > limits.max_total_tokens:
        raise BudgetExceededError(
            f"Next call could use up to {worst_case} tokens; the run limit is "
            f"{limits.max_total_tokens}",
            details={"limit": "max_total_tokens"},
        )


MICROUSD_PER_USD = 1_000_000


def check_cost(
    *,
    worst_case_microusd: int | None,
    run_spent_microusd: int,
    project_spent_microusd: int,
    run_limit_microusd: int | None,
    project_limit_microusd: int | None,
) -> None:
    """Refuse a step whose worst-case cost could pass the run's or the project's cost limit.

    Fails closed: with a limit set, a model without a recorded price cannot be called at all.
    """
    if run_limit_microusd is None and project_limit_microusd is None:
        return
    if worst_case_microusd is None:
        raise BudgetExceededError(
            "The model has no recorded price, so the cost limit cannot be enforced",
            details={"limit": "cost_unknown"},
        )
    for spent, limit, name in (
        (run_spent_microusd, run_limit_microusd, "run_cost"),
        (project_spent_microusd, project_limit_microusd, "project_cost"),
    ):
        if limit is not None and spent + worst_case_microusd > limit:
            raise BudgetExceededError(
                f"The next step could cost up to ${worst_case_microusd / MICROUSD_PER_USD:.4f}; "
                f"the {name.replace('_', ' ')} limit is ${limit / MICROUSD_PER_USD:.4f} and "
                f"${spent / MICROUSD_PER_USD:.4f} is spent",
                details={"limit": name},
            )
