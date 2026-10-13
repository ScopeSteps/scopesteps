from dataclasses import dataclass, field
from typing import Literal

from scopesteps.agent.application.checks import USER_STORY, check_draft, requirement_blocks
from scopesteps.agent.application.drafting import (
    DEFAULT_PROMPT,
    DRAFT_PROMPT_VERSION,
    PROMPT_CHECKS,
    DraftOutcome,
    PromptName,
    draft_single_pass,
    prompt_version,
)
from scopesteps.agent.application.ports import ModelProvider
from scopesteps.agent.application.runs import AgentRuntime
from scopesteps.agent.application.schemas import (
    DRAFT_SCHEMA_VERSION,
    AnyDraft,
    DraftBacklog,
    DraftBacklogV1,
    SourceBlockInput,
    parse_draft,
)
from scopesteps.agent.application.tracing import trace_scope
from scopesteps.agent.domain.budget import MICROUSD_PER_USD, RunLimits
from scopesteps.agent.domain.ids import QuestionId, RunId
from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    Usage,
)
from scopesteps.agent.domain.pricing import PRICES_CHECKED, estimate_cost_usd
from scopesteps.agent.infrastructure.providers.gemini import GeminiProvider, ThinkingLevel
from scopesteps.agent.infrastructure.providers.openai_compatible import OpenAICompatibleProvider
from scopesteps.agent.infrastructure.providers.traced import TracedProvider, TraceSink, log_sink

ProviderName = Literal["gemini", "groq"]
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


@dataclass(frozen=True)
class ModelConfig:
    """Everything needed to build the one provider a process uses."""

    provider: ProviderName
    model_id: str
    api_key: str = field(repr=False)
    timeout_seconds: float
    thinking_level: ThinkingLevel
    base_url: str | None = None
    max_output_tokens_cap: int | None = None
    """Lower ceiling for one call's output, for providers whose per-minute token allowance counts
    the requested maximum."""


def create_model_provider(
    config: ModelConfig, *, trace_sink: TraceSink = log_sink
) -> ModelProvider:
    """The one place a provider is chosen. There is deliberately no fallback list: switching
    provider is an explicit configuration change (ADR 0004, ADR 0006).

    Every call is traced (content-free, OpenTelemetry GenAI attribute names) to `trace_sink`.
    """
    inner: ModelProvider
    match config.provider:
        case "gemini":
            inner = GeminiProvider(
                api_key=config.api_key,
                model_id=config.model_id,
                timeout_seconds=config.timeout_seconds,
                thinking_level=config.thinking_level,
            )
            name = "gcp.gemini"
        case "groq":
            inner = OpenAICompatibleProvider(
                provider="groq",
                api_key=config.api_key,
                model_id=config.model_id,
                base_url=config.base_url or GROQ_BASE_URL,
                timeout_seconds=config.timeout_seconds,
                thinking_level=config.thinking_level,
                max_output_tokens_cap=config.max_output_tokens_cap,
            )
            name = "groq"
    return TracedProvider(inner, provider_name=name, model_id=config.model_id, sink=trace_sink)


__all__ = [
    "DEFAULT_PROMPT",
    "DRAFT_PROMPT_VERSION",
    "DRAFT_SCHEMA_VERSION",
    "GROQ_BASE_URL",
    "MICROUSD_PER_USD",
    "PRICES_CHECKED",
    "PROMPT_CHECKS",
    "USER_STORY",
    "AgentRuntime",
    "AnyDraft",
    "DraftBacklog",
    "DraftBacklogV1",
    "DraftOutcome",
    "ModelConfig",
    "ModelProvider",
    "ModelProviderError",
    "ModelRequest",
    "ModelResult",
    "ModelTurn",
    "PromptName",
    "ProviderName",
    "QuestionId",
    "RunId",
    "RunLimits",
    "SourceBlockInput",
    "ThinkingLevel",
    "TraceSink",
    "Usage",
    "check_draft",
    "create_model_provider",
    "draft_single_pass",
    "estimate_cost_usd",
    "parse_draft",
    "prompt_version",
    "requirement_blocks",
    "trace_scope",
]
