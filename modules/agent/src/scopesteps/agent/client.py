from typing import Literal, NewType
from uuid import UUID

from scopesteps.agent.application.drafting import (
    DRAFT_PROMPT_VERSION,
    DraftOutcome,
    SourceBlockInput,
    draft_single_pass,
)
from scopesteps.agent.application.ports import ModelProvider
from scopesteps.agent.application.schemas import DRAFT_SCHEMA_VERSION, DraftBacklog
from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    Usage,
)
from scopesteps.agent.infrastructure.providers.gemini import GeminiProvider, ThinkingLevel

RunId = NewType("RunId", UUID)
QuestionId = NewType("QuestionId", UUID)


def create_model_provider(
    *,
    provider: Literal["gemini"],
    api_key: str,
    model_id: str,
    timeout_seconds: float,
    thinking_level: ThinkingLevel,
) -> ModelProvider:
    """The one place a provider is chosen. There is deliberately no fallback list (ADR 0004)."""
    match provider:
        case "gemini":
            return GeminiProvider(
                api_key=api_key,
                model_id=model_id,
                timeout_seconds=timeout_seconds,
                thinking_level=thinking_level,
            )


__all__ = [
    "DRAFT_PROMPT_VERSION",
    "DRAFT_SCHEMA_VERSION",
    "DraftBacklog",
    "DraftOutcome",
    "ModelProvider",
    "ModelProviderError",
    "ModelRequest",
    "ModelResult",
    "ModelTurn",
    "QuestionId",
    "RunId",
    "SourceBlockInput",
    "Usage",
    "create_model_provider",
    "draft_single_pass",
]
