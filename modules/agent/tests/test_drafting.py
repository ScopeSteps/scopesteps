import json

from scopesteps.agent.application.drafting import (
    ANSWERS_INSTRUCTION,
    DRAFT_PROMPT_VERSION,
    SourceBlockInput,
    draft_single_pass,
)
from scopesteps.agent.domain.model import ModelResult, ModelTurn, Usage, UserMessage
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider

BLOCKS = [SourceBlockInput("B1", "brief.md paragraph 1", "Users can book a room.")]
VALID = json.dumps({"statements": [], "items": [], "questions": []})
INVALID = json.dumps({"statements": [], "items": [{"ref": "S1"}], "questions": []})


def _result(text: str, tokens: int = 10) -> ModelResult:
    return ModelResult(
        provider="test",
        model_id="model-x",
        turn=ModelTurn(steps=({"type": "model_output", "text": text},)),
        text=text,
        tool_calls=(),
        finish_reason="completed",
        usage=Usage(total_tokens=tokens),
        latency_ms=5,
    )


def test_valid_draft_takes_one_call() -> None:
    provider = ScriptedProvider([_result(VALID)])

    outcome = draft_single_pass(provider, BLOCKS, max_output_tokens=100)

    assert outcome.draft is not None
    assert (outcome.calls, outcome.repaired, outcome.error) == (1, False, None)
    request = provider.requests[0]
    assert request.output_schema is not None
    assert request.tools == ()
    assert "[B1] (brief.md paragraph 1) Users can book a room." in str(request.history[0])


def test_invalid_draft_gets_one_repair_with_the_errors_and_its_own_output() -> None:
    provider = ScriptedProvider([_result(INVALID, 10), _result(VALID, 15)])

    outcome = draft_single_pass(provider, BLOCKS, max_output_tokens=100)

    assert outcome.draft is not None
    assert (outcome.calls, outcome.repaired) == (2, True)
    assert outcome.usage.total_tokens == 25
    repair = provider.requests[1].history
    assert repair[1] == _result(INVALID).turn
    assert isinstance(repair[2], UserMessage)
    assert "items.0" in repair[2].text


def test_draft_stays_invalid_after_the_repair_allowance() -> None:
    provider = ScriptedProvider([_result(INVALID), _result("not json")])

    outcome = draft_single_pass(provider, BLOCKS, max_output_tokens=100)

    assert outcome.draft is None
    assert outcome.error is not None
    assert outcome.calls == 2


def test_answers_mode_tells_the_model_to_treat_answers_as_sources() -> None:
    provider = ScriptedProvider([_result(VALID)])

    draft_single_pass(provider, BLOCKS, max_output_tokens=100, with_answers=True)

    assert ANSWERS_INSTRUCTION in str(provider.requests[0].history[0])


def test_prompt_version_names_the_prompt_and_its_hash() -> None:
    name, digest = DRAFT_PROMPT_VERSION.split("+")

    assert name == "draft-v1"
    assert len(digest) == 12
