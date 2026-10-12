"""Provider-neutral model request/result types. Only provider adapters translate these."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from scopesteps.kernel import DomainError

ToolChoice = Literal["auto", "any", "none", "validated"]
FinishReason = Literal["completed", "tool_calls", "max_tokens", "blocked", "other"]
ProviderErrorKind = Literal[
    "quota", "unavailable", "timeout", "auth", "invalid_request", "blocked", "malformed_response"
]
JsonObject = Mapping[str, object]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: JsonObject


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: JsonObject


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    output: JsonObject
    is_error: bool = False


@dataclass(frozen=True)
class UserMessage:
    text: str


@dataclass(frozen=True)
class ModelTurn:
    """The provider's own output steps, replayed verbatim on the next call.

    Gemini 3 needs its thought signatures sent back unchanged when requests are stateless.
    """

    steps: tuple[JsonObject, ...]


@dataclass(frozen=True)
class ToolResults:
    results: tuple[ToolResult, ...]


Turn = UserMessage | ModelTurn | ToolResults


@dataclass(frozen=True)
class ModelRequest:
    system_instruction: str
    history: tuple[Turn, ...]
    max_output_tokens: int
    tools: tuple[ToolSpec, ...] = ()
    tool_choice: ToolChoice = "auto"
    allowed_tools: tuple[str, ...] = ()
    output_schema: JsonObject | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class ModelResult:
    provider: str
    model_id: str
    turn: ModelTurn
    text: str | None
    tool_calls: tuple[ToolCall, ...]
    finish_reason: FinishReason
    usage: Usage
    latency_ms: int
    provider_status: str = ""
    warnings: tuple[str, ...] = field(default=())


class ModelProviderError(DomainError):
    """A classified provider failure. Never carries prompts, source text or credentials."""

    code = "MODEL_PROVIDER_ERROR"

    def __init__(
        self,
        kind: ProviderErrorKind,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(
            message,
            details={"kind": kind, "status_code": status_code},
        )
        self.kind = kind
        self.retryable = kind in {"quota", "unavailable", "timeout"}
        self.retry_after_seconds = retry_after_seconds
        self.status_code = status_code
