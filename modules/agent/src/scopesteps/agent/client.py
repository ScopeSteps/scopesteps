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
from scopesteps.agent.infrastructure.providers.traced import TracedProvider, TraceSink, log_sink


def create_model_provider(
    *,
    provider: Literal["gemini"],
    api_key: str,
    model_id: str,
    timeout_seconds: float,
    thinking_level: ThinkingLevel,
    trace_sink: TraceSink = log_sink,
) -> ModelProvider:
    """The one place a provider is chosen. There is deliberately no fallback list (ADR 0004).

    Every call is traced (content-free, OpenTelemetry GenAI attribute names) to `trace_sink`.
    """
    match provider:
        case "gemini":
            inner = GeminiProvider(
                api_key=api_key,
                model_id=model_id,
                timeout_seconds=timeout_seconds,
                thinking_level=thinking_level,
            )
            return TracedProvider(
                inner, provider_name="gcp.gemini", model_id=model_id, sink=trace_sink
            )


__all__ = [
    "DEFAULT_PROMPT",
    "DRAFT_PROMPT_VERSION",
    "DRAFT_SCHEMA_VERSION",
    "MICROUSD_PER_USD",
    "PRICES_CHECKED",
    "PROMPT_CHECKS",
    "USER_STORY",
    "AgentRuntime",
    "AnyDraft",
    "DraftBacklog",
    "DraftBacklogV1",
    "DraftOutcome",
    "ModelProvider",
    "ModelProviderError",
    "ModelRequest",
    "ModelResult",
    "ModelTurn",
    "PromptName",
    "QuestionId",
    "RunId",
    "RunLimits",
    "SourceBlockInput",
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
