import json
from pathlib import Path

import pytest

from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    ToolCall,
    Usage,
    UserMessage,
)
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.agent.infrastructure.providers.replay import (
    REPLAY_FORMAT,
    RecordingProvider,
    ReplayProvider,
)

EXPLORE = ModelRequest("explore prompt", (UserMessage("sources"),), max_output_tokens=100)
DRAFT = ModelRequest("draft prompt", (UserMessage("sources"),), max_output_tokens=100)


def _result(text: str | None, calls: tuple[ToolCall, ...] = ()) -> ModelResult:
    return ModelResult(
        provider="gemini",
        model_id="gemini-3.5-flash-lite",
        turn=ModelTurn(({"type": "model_output", "text": text or ""},)),
        text=text,
        tool_calls=calls,
        finish_reason="tool_calls" if calls else "completed",
        usage=Usage(input_tokens=900, output_tokens=100, total_tokens=1000),
        latency_ms=1200,
    )


ASK = _result(None, (ToolCall("call-1", "request_clarification", {"questions": []}),))
DRAFTED = _result('{"items": []}')


def _record(path: Path) -> None:
    live = ScriptedProvider([ASK, DRAFTED])
    recorder = RecordingProvider(live, path, provider="gemini", model_id="gemini-3.5-flash-lite")
    assert recorder.generate(EXPLORE) == ASK
    assert recorder.generate(DRAFT) == DRAFTED


def test_a_recording_replays_the_same_results_in_order_without_a_model(tmp_path: Path) -> None:
    path = tmp_path / "demo.json"
    _record(path)

    replay = ReplayProvider.from_file(path)

    explored, drafted = replay.generate(EXPLORE), replay.generate(DRAFT)
    assert explored.tool_calls == ASK.tool_calls
    assert explored.turn == ASK.turn
    assert drafted.text == DRAFTED.text
    assert drafted.usage == DRAFTED.usage
    assert {explored.provider, drafted.provider} == {"replay"}
    assert replay.model_id == "gemini-3.5-flash-lite"
    assert replay.remaining == 0


def test_a_recording_holds_results_but_never_the_prompts(tmp_path: Path) -> None:
    path = tmp_path / "demo.json"
    _record(path)

    recording = json.loads(path.read_text(encoding="utf-8"))

    assert recording["format"] == REPLAY_FORMAT
    assert len(recording["calls"]) == 2
    assert "explore prompt" not in path.read_text(encoding="utf-8")
    assert "sources" not in path.read_text(encoding="utf-8")


def test_a_failed_live_call_is_not_recorded(tmp_path: Path) -> None:
    path = tmp_path / "demo.json"
    live = ScriptedProvider([ModelProviderError("unavailable", "overloaded"), DRAFTED])
    recorder = RecordingProvider(live, path, provider="gemini", model_id="gemini-3.5-flash-lite")

    with pytest.raises(ModelProviderError):
        recorder.generate(DRAFT)
    recorder.generate(DRAFT)

    assert len(json.loads(path.read_text(encoding="utf-8"))["calls"]) == 1


def test_a_step_out_of_order_is_refused_and_does_not_use_up_the_recording(
    tmp_path: Path,
) -> None:
    path = tmp_path / "demo.json"
    _record(path)
    replay = ReplayProvider.from_file(path)

    with pytest.raises(ModelProviderError, match="does not match the recording") as refused:
        replay.generate(DRAFT)

    assert not refused.value.retryable
    assert replay.remaining == 2
    assert replay.generate(EXPLORE).tool_calls == ASK.tool_calls


def test_a_finished_replay_refuses_further_calls(tmp_path: Path) -> None:
    path = tmp_path / "demo.json"
    _record(path)
    replay = ReplayProvider.from_file(path)
    replay.generate(EXPLORE)
    replay.generate(DRAFT)

    with pytest.raises(ModelProviderError, match="no more recorded calls"):
        replay.generate(DRAFT)


def test_a_file_that_is_not_a_recording_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"calls": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="not a scopesteps-model-replay"):
        ReplayProvider.from_file(path)
