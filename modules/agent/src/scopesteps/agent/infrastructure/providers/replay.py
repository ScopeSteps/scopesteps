"""Record a live model's results once, then replay them in order with no model behind them.

A replay lets the web app be demonstrated and tested end to end offline. It is never a live run:
runs made with it are pinned to the provider name `replay`, so the app can say so. Only results
are recorded, never prompts, and the same sources and answers must be given in the same order as
when it was recorded; a request whose system prompt differs from the recorded one is refused.
"""

import hashlib
import json
import threading
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from scopesteps.agent.application.ports import ModelProvider
from scopesteps.agent.domain.model import (
    FinishReason,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    ToolCall,
    Usage,
)

REPLAY_FORMAT = "scopesteps-model-replay.v1"
REPLAY_PROVIDER = "replay"


def instruction_digest(request: ModelRequest) -> str:
    """Which prompt a call was made with, without storing the prompt."""
    return hashlib.sha256(request.system_instruction.encode()).hexdigest()[:16]


class RecordingProvider:
    """Passes every call to the live provider and appends its result to a replay file.

    The file is rewritten after each call, so a recording stopped midway is still usable up to
    its last call. Failed calls are not recorded: a replay shows the run as it succeeded.
    """

    def __init__(self, inner: ModelProvider, path: Path, *, provider: str, model_id: str) -> None:
        self._inner = inner
        self._path = path
        self._lock = threading.Lock()
        self._recording: dict[str, Any] = {
            "format": REPLAY_FORMAT,
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "provider": provider,
            "model_id": model_id,
            "calls": [],
        }

    def generate(self, request: ModelRequest) -> ModelResult:
        result = self._inner.generate(request)
        with self._lock:
            calls = cast(list[dict[str, Any]], self._recording["calls"])
            calls.append({"instruction": instruction_digest(request), "result": asdict(result)})
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._recording, indent=1) + "\n", encoding="utf-8")
        return result


class ReplayProvider:
    """Returns a recording's results in the order they were recorded, one per call."""

    def __init__(self, calls: Sequence[tuple[str, ModelResult]], *, model_id: str) -> None:
        self._calls = list(calls)
        self._next = 0
        self._lock = threading.Lock()
        self.model_id = model_id

    @classmethod
    def from_file(cls, path: Path) -> ReplayProvider:
        recording = json.loads(path.read_text(encoding="utf-8"))
        if recording.get("format") != REPLAY_FORMAT:
            raise ValueError(f"{path} is not a {REPLAY_FORMAT} recording")
        calls = [(str(call["instruction"]), _result(call["result"])) for call in recording["calls"]]
        return cls(calls, model_id=str(recording["model_id"]))

    @property
    def remaining(self) -> int:
        return len(self._calls) - self._next

    def generate(self, request: ModelRequest) -> ModelResult:
        with self._lock:
            if self._next >= len(self._calls):
                raise ModelProviderError(
                    "invalid_request",
                    "The replay has no more recorded calls. Restart the API to replay it again.",
                )
            instruction, result = self._calls[self._next]
            if instruction != instruction_digest(request):
                raise ModelProviderError(
                    "invalid_request",
                    "This step does not match the recording. A replay only follows the recorded "
                    "demonstration, with the same sources and answers in the same order.",
                )
            self._next += 1
            return result


def _result(data: Mapping[str, Any]) -> ModelResult:
    calls = tuple(ToolCall(**call) for call in data["tool_calls"])
    return ModelResult(
        provider=REPLAY_PROVIDER,
        model_id=str(data["model_id"]),
        turn=ModelTurn(steps=tuple(data["turn"]["steps"])),
        text=data["text"],
        tool_calls=calls,
        finish_reason=cast(FinishReason, data["finish_reason"]),
        usage=Usage(**data["usage"]),
        # A replay answers at once; the recorded latency stays in the recording.
        latency_ms=0,
        provider_status=str(data.get("provider_status", "")),
        warnings=tuple(data.get("warnings", ())),
        usage_reported=bool(data.get("usage_reported", True)),
        output_budget=data.get("output_budget"),
    )
