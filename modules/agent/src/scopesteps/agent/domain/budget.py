"""Run limits, checked before every model call. Resuming a run never resets the counters."""

import math
from dataclasses import dataclass, replace

from scopesteps.agent.domain.model import ModelResult
from scopesteps.kernel import DomainError
from scopesteps.kernel.errors import PayloadTooLargeError

# Deliberately pessimistic (about 3 characters per token) so the pre-call check errs towards
# stopping. Real usage reported by the provider replaces the estimate after each call.
CHARS_PER_TOKEN_ESTIMATE = 3


# An English word with the space after it averages about six characters, so an estimate in
# tokens can be told to people in words.
CHARS_PER_WORD = 6


class BudgetExceededError(DomainError):
    code = "RUN_BUDGET_EXCEEDED"


class RunInputTooLargeError(BudgetExceededError, PayloadTooLargeError):
    """The sources do not fit what the model reads in one request, or a run on them could not
    finish within the run's limits. Raised before any call, so no run is left half done."""

    code = "RUN_INPUT_TOO_LARGE"


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


def words_for(tokens: int) -> int:
    """About how many words `tokens` estimated tokens hold, for messages people read."""
    return tokens * CHARS_PER_TOKEN_ESTIMATE // CHARS_PER_WORD


def check_request_fits(
    estimated_input_tokens: int, limits: RunLimits, max_request_tokens: int | None
) -> None:
    """Refuse a call whose input and output together could not fit one request to the model."""
    if max_request_tokens is None:
        return
    room = max_request_tokens - limits.max_output_tokens_per_call
    if estimated_input_tokens > room:
        raise RunInputTooLargeError(
            f"The selected sources are too long for the model to read at once: they hold about "
            f"{words_for(estimated_input_tokens):,} words with the instructions, and it reads "
            f"about {words_for(max(room, 0)):,}. Choose fewer sources or shorter ones.",
            details={
                "limit": "max_request_tokens",
                "estimated_input_tokens": estimated_input_tokens,
                "max_request_tokens": max_request_tokens,
            },
        )


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
