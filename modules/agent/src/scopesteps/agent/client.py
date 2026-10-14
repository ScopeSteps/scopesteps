from dataclasses import dataclass, field
from typing import Literal

from scopesteps.agent.application.checks import USER_STORY, check_draft, requirement_blocks
from scopesteps.agent.application.drafting import (
    DEFAULT_PROMPT,
    DRAFT_PROMPT_VERSION,
    PROMPT_CHECKS,
    PROMPT_SCHEMAS,
    DraftOutcome,
    PromptName,
    draft_single_pass,
    prompt_version,
)
from scopesteps.agent.application.fallback import CircuitBreaker, ServedModel
from scopesteps.agent.application.offline import Answerer, OfflineRun, run_offline
from scopesteps.agent.application.ports import ModelProvider, Passage
from scopesteps.agent.application.runs import AgentRuntime
from scopesteps.agent.application.schemas import (
    DRAFT_SCHEMA_VERSION,
    AnyDraft,
    DraftBacklog,
    DraftBacklogV1,
    SourceBlockInput,
    parse_draft,
)
from scopesteps.agent.application.steps import AGENT_EXPLORE, AGENT_PROMPT_VERSION, ExploreName
from scopesteps.agent.application.tracing import trace_scope
from scopesteps.agent.domain.budget import MICROUSD_PER_USD, RunLimits
from scopesteps.agent.domain.ids import QuestionId, RunId
from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    ToolCall,
    Usage,
)
from scopesteps.agent.domain.pricing import PRICES_CHECKED, estimate_cost_usd
from scopesteps.agent.domain.providers import ProviderProfile
from scopesteps.agent.domain.rate import TokenWindow
from scopesteps.agent.domain.run import Question, QuestionStatus, RunStatus
from scopesteps.agent.infrastructure.providers import gemini, groq
from scopesteps.agent.infrastructure.providers.gemini import GeminiProvider, ThinkingLevel
from scopesteps.agent.infrastructure.providers.openai_compatible import OpenAICompatibleProvider
from scopesteps.agent.infrastructure.providers.paced import PacedProvider
from scopesteps.agent.infrastructure.providers.traced import TracedProvider, TraceSink, log_sink

ProviderName = Literal["gemini", "groq"]
PROFILES: dict[ProviderName, ProviderProfile] = {"gemini": gemini.PROFILE, "groq": groq.PROFILE}


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
    """Lower ceiling for one call's output, so one call fits the per-minute token allowance."""
    tokens_per_minute: int | None = None
    """The provider's per-minute token allowance, for pacing batch callers (`paced`)."""


def paced(provider: ModelProvider, config: ModelConfig) -> ModelProvider:
    """Wrap a provider so batch tools wait for the per-minute token allowance instead of hitting
    429s. Request-driven runs do not use this; a step must finish within its lease."""
    if config.tokens_per_minute is None:
        return provider
    return PacedProvider(provider, TokenWindow(config.tokens_per_minute))


def create_model_provider(
    config: ModelConfig, *, trace_sink: TraceSink = log_sink
) -> ModelProvider:
    """The one place a provider is chosen. There is deliberately no fallback list: switching
    provider is an explicit configuration change (ADR 0004, ADR 0006).

    Every call is traced (content-free, OpenTelemetry GenAI attribute names) to `trace_sink`.
    """
    profile = PROFILES[config.provider]
    inner: ModelProvider
    match profile.api:
        case "gemini_interactions":
            inner = GeminiProvider(
                api_key=config.api_key,
                model_id=config.model_id,
                timeout_seconds=config.timeout_seconds,
                thinking_level=config.thinking_level,
                base_url=config.base_url,
            )
        case _:
            inner = OpenAICompatibleProvider(
                provider=profile.name,
                api_key=config.api_key,
                model_id=config.model_id,
                base_url=config.base_url or profile.base_url or "",
                timeout_seconds=config.timeout_seconds,
                thinking_level=config.thinking_level,
                max_output_tokens_cap=config.max_output_tokens_cap,
                reasoning_effort_models=profile.reasoning_effort_models,
                request_token_limit=config.tokens_per_minute,
                request_chars_per_token=profile.request_chars_per_token,
            )
    return TracedProvider(
        inner, provider_name=profile.trace_name, model_id=config.model_id, sink=trace_sink
    )


__all__ = [
    "AGENT_EXPLORE",
    "AGENT_PROMPT_VERSION",
    "DEFAULT_PROMPT",
    "DRAFT_PROMPT_VERSION",
    "DRAFT_SCHEMA_VERSION",
    "MICROUSD_PER_USD",
    "PRICES_CHECKED",
    "PROFILES",
    "PROMPT_CHECKS",
    "PROMPT_SCHEMAS",
    "USER_STORY",
    "AgentRuntime",
    "Answerer",
    "AnyDraft",
    "CircuitBreaker",
    "DraftBacklog",
    "DraftBacklogV1",
    "DraftOutcome",
    "ExploreName",
    "ModelConfig",
    "ModelProvider",
    "ModelProviderError",
    "ModelRequest",
    "ModelResult",
    "ModelTurn",
    "OfflineRun",
    "Passage",
    "PromptName",
    "ProviderName",
    "ProviderProfile",
    "Question",
    "QuestionId",
    "QuestionStatus",
    "RunId",
    "RunLimits",
    "RunStatus",
    "ServedModel",
    "SourceBlockInput",
    "ThinkingLevel",
    "ToolCall",
    "TraceSink",
    "Usage",
    "check_draft",
    "create_model_provider",
    "draft_single_pass",
    "estimate_cost_usd",
    "paced",
    "parse_draft",
    "prompt_version",
    "requirement_blocks",
    "run_offline",
    "trace_scope",
]
