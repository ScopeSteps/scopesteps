import pytest

from scopesteps.agent.application.schemas import SourceBlockInput
from scopesteps.agent.application.tools import Clarification, fence, run_tool
from scopesteps.agent.domain.budget import (
    BudgetExceededError,
    RunCounters,
    RunLimits,
    check_can_call,
    check_cost,
)
from scopesteps.agent.domain.model import ToolCall, ToolResult

BLOCKS = [SourceBlockInput("B1", "brief paragraph 1", "Users <b>book</b> rooms.")]
LIMITS = RunLimits(
    max_turns=3, max_tool_calls=8, max_output_tokens_per_call=100, max_total_tokens=1000
)


def test_a_step_reserves_room_for_every_call_it_may_make() -> None:
    check_can_call(RunCounters(model_turns=1), LIMITS, 10, calls=2)

    with pytest.raises(BudgetExceededError, match="3 model turns"):
        check_can_call(RunCounters(model_turns=2), LIMITS, 10, calls=2)


@pytest.mark.parametrize(
    ("kwargs", "limit"),
    [
        ({"run_spent_microusd": 900, "run_limit_microusd": 1000}, "run_cost"),
        ({"project_spent_microusd": 900, "project_limit_microusd": 1000}, "project_cost"),
    ],
)
def test_cost_limits_count_what_is_spent_plus_the_worst_case(
    kwargs: dict[str, int], limit: str
) -> None:
    arguments = {
        "worst_case_microusd": 200,
        "run_spent_microusd": 0,
        "project_spent_microusd": 0,
        "run_limit_microusd": None,
        "project_limit_microusd": None,
    } | kwargs

    with pytest.raises(BudgetExceededError) as raised:
        check_cost(**arguments)  # type: ignore[arg-type]

    assert raised.value.details == {"limit": limit}


def test_an_unpriced_model_cannot_be_called_under_a_cost_limit() -> None:
    with pytest.raises(BudgetExceededError, match="no recorded price"):
        check_cost(
            worst_case_microusd=None,
            run_spent_microusd=0,
            project_spent_microusd=0,
            run_limit_microusd=1000,
            project_limit_microusd=None,
        )


def test_tool_results_fence_and_escape_source_text() -> None:
    assert fence(BLOCKS[0]) == (
        '<source id="B1" label="brief paragraph 1">Users &lt;b&gt;book&lt;/b&gt; rooms.</source>'
    )


def test_lookup_source_searches_only_the_runs_blocks() -> None:
    result = run_tool(ToolCall("c1", "lookup_source", {"query": "rooms"}), BLOCKS, may_ask=True)

    assert isinstance(result, ToolResult)
    assert result.output == {"blocks": [fence(BLOCKS[0])]}


@pytest.mark.parametrize(
    ("call", "may_ask", "message"),
    [
        (ToolCall("c1", "publish_backlog", {}), True, "not available"),
        (ToolCall("c1", "request_clarification", {"questions": []}), True, "questions"),
        (
            ToolCall(
                "c1",
                "request_clarification",
                {
                    "questions": [
                        {
                            "subject": "s",
                            "question": "q",
                            "why_it_matters": "w",
                            "block_ids": ["B9"],
                        }
                    ]
                },
            ),
            True,
            "Unknown block ids: B9",
        ),
        (ToolCall("c1", "request_clarification", {"questions": []}), False, "No clarification"),
    ],
)
def test_tool_mistakes_come_back_as_error_results(
    call: ToolCall, may_ask: bool, message: str
) -> None:
    result = run_tool(call, BLOCKS, may_ask=may_ask)

    assert isinstance(result, ToolResult)
    assert result.is_error
    assert message in str(result.output["error"])


def test_a_valid_clarification_pauses_instead_of_returning_a_result() -> None:
    question = {"subject": "s", "question": "q", "why_it_matters": "w", "block_ids": ["B1"]}

    result = run_tool(
        ToolCall("c1", "request_clarification", {"questions": [question]}), BLOCKS, may_ask=True
    )

    assert isinstance(result, Clarification)
    assert result.call_id == "c1"
