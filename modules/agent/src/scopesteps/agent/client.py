from typing import Literal, NewType
from uuid import UUID

from scopesteps.agent.application.checks import USER_STORY, check_draft
from scopesteps.agent.application.drafting import (
    DEFAULT_PROMPT,
    DRAFT_PROMPT_VERSION,
    DraftOutcome,
    PromptName,
    draft_single_pass,
    prompt_version,
)
from scopesteps.agent.application.ports import ModelProvider
from scopesteps.agent.application.schemas import (
    DRAFT_SCHEMA_VERSION,
    DraftBacklog,
    SourceBlockInput,
)
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
    "DEFAULT_PROMPT",
    "DRAFT_PROMPT_VERSION",
    "DRAFT_SCHEMA_VERSION",
    "USER_STORY",
    "DraftBacklog",
    "DraftOutcome",
    "ModelProvider",
    "ModelProviderError",
    "ModelRequest",
    "ModelResult",
    "ModelTurn",
    "PromptName",
    "QuestionId",
    "RunId",
    "SourceBlockInput",
    "Usage",
    "check_draft",
    "create_model_provider",
    "draft_single_pass",
    "prompt_version",
]
