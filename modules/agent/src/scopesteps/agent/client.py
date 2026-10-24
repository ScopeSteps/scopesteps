from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from scopesteps.agent.application.changing import (
    CHANGE_PROMPT_VERSION,
    CHANGE_REQUEST_KIND,
    CHANGE_RUN,
    CHANGE_SCHEMA_VERSION,
    BaselineLabels,
    ChangeName,
    ChangeResult,
    ChangeSetOutput,
    change_prompt_version,
    change_schema_version,
)
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
from scopesteps.agent.application.offline import (
    Answerer,
    EarlierMessage,
    OfflineChange,
    OfflineReply,
    OfflineRun,
    RecordedAnswer,
    analyze_change_offline,
    reply_offline,
    run_offline,
)
from scopesteps.agent.application.ports import ModelProvider, Passage
from scopesteps.agent.application.replying import (
    CONVERSATION_REPLY,
    REPLY_PROMPT_VERSION,
    REPLY_SCHEMA_VERSION,
    REPLY_SCHEMAS,
    ReplyName,
    reply_prompt_version,
)
from scopesteps.agent.application.runs import AgentRuntime
from scopesteps.agent.application.schemas import (
    DRAFT_SCHEMA_VERSION,
    AnyDraft,
    DraftBacklog,
    DraftBacklogV1,
    DraftBacklogV4,
    DraftBacklogV5,
    DraftPerson,
    DraftPersonV5,
    SourceBlockInput,
    SpeakerNote,
    parse_draft,
)
from scopesteps.agent.application.speakers import Participants, participants_of
from scopesteps.agent.application.steps import AGENT_EXPLORE, AGENT_PROMPT_VERSION, ExploreName
from scopesteps.agent.application.tracing import trace_scope
from scopesteps.agent.domain.budget import MICROUSD_PER_USD, RunLimits
from scopesteps.agent.domain.conversation import MAX_MESSAGE_CHARS, CitedPassage, Claim
from scopesteps.agent.domain.ids import MessageId, QuestionId, RunId
from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    ToolCall,
    Usage,
    UserMessage,
)
from scopesteps.agent.domain.pricing import PRICES_CHECKED, estimate_cost_usd
from scopesteps.agent.domain.providers import ProviderProfile
from scopesteps.agent.domain.rate import TokenWindow
from scopesteps.agent.domain.run import Question, QuestionStatus, RunStatus
from scopesteps.agent.infrastructure.providers import gemini, groq
from scopesteps.agent.infrastructure.providers.gemini import GeminiProvider, ThinkingLevel
from scopesteps.agent.infrastructure.providers.openai_compatible import OpenAICompatibleProvider
from scopesteps.agent.infrastructure.providers.paced import PacedProvider
from scopesteps.agent.infrastructure.providers.replay import (
    REPLAY_PROVIDER,
    RecordingProvider,
    ReplayProvider,
)
from scopesteps.agent.infrastructure.providers.traced import TracedProvider, TraceSink, log_sink
from scopesteps.agent.infrastructure.repository import SqlRunRepository
from scopesteps.projects.client import ProjectId

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


def create_replay_provider(
    path: Path, *, trace_sink: TraceSink = log_sink
) -> tuple[ModelProvider, str]:
    """A provider that replays a recording, and the model it was recorded with. Runs made with it
    are pinned to the provider name `REPLAY_PROVIDER`, never to the live provider's."""
    replay = ReplayProvider.from_file(path)
    traced = TracedProvider(
        replay, provider_name=REPLAY_PROVIDER, model_id=replay.model_id, sink=trace_sink
    )
    return traced, replay.model_id


def recording(provider: ModelProvider, path: Path, config: ModelConfig) -> ModelProvider:
    """Wrap a live provider so each successful result is also written to a replay file."""
    return RecordingProvider(provider, path, provider=config.provider, model_id=config.model_id)


def runs_pinning_sources(
    session: Session, project_id: ProjectId, source_version_ids: Collection[UUID]
) -> list[RunId]:
    """The project's runs, in any status, that pinned any of the source versions. Performs no
    access check."""
    return SqlRunRepository(session).runs_pinning(project_id, source_version_ids)


__all__ = [
    "AGENT_EXPLORE",
    "AGENT_PROMPT_VERSION",
    "CHANGE_PROMPT_VERSION",
    "CHANGE_REQUEST_KIND",
    "CHANGE_RUN",
    "CHANGE_SCHEMA_VERSION",
    "CONVERSATION_REPLY",
    "DEFAULT_PROMPT",
    "DRAFT_PROMPT_VERSION",
    "DRAFT_SCHEMA_VERSION",
    "MAX_MESSAGE_CHARS",
    "MICROUSD_PER_USD",
    "PRICES_CHECKED",
    "PROFILES",
    "PROMPT_CHECKS",
    "PROMPT_SCHEMAS",
    "REPLAY_PROVIDER",
    "REPLY_PROMPT_VERSION",
    "REPLY_SCHEMAS",
    "REPLY_SCHEMA_VERSION",
    "USER_STORY",
    "AgentRuntime",
    "Answerer",
    "AnyDraft",
    "BaselineLabels",
    "ChangeName",
    "ChangeResult",
    "ChangeSetOutput",
    "CircuitBreaker",
    "CitedPassage",
    "Claim",
    "DraftBacklog",
    "DraftBacklogV1",
    "DraftBacklogV4",
    "DraftBacklogV5",
    "DraftOutcome",
    "DraftPerson",
    "DraftPersonV5",
    "EarlierMessage",
    "ExploreName",
    "MessageId",
    "ModelConfig",
    "ModelProvider",
    "ModelProviderError",
    "ModelRequest",
    "ModelResult",
    "ModelTurn",
    "OfflineChange",
    "OfflineReply",
    "OfflineRun",
    "Participants",
    "Passage",
    "PromptName",
    "ProviderName",
    "ProviderProfile",
    "Question",
    "QuestionId",
    "QuestionStatus",
    "RecordedAnswer",
    "ReplyName",
    "RunId",
    "RunLimits",
    "RunStatus",
    "ServedModel",
    "SourceBlockInput",
    "SpeakerNote",
    "ThinkingLevel",
    "ToolCall",
    "TraceSink",
    "Usage",
    "UserMessage",
    "analyze_change_offline",
    "change_prompt_version",
    "change_schema_version",
    "check_draft",
    "create_model_provider",
    "create_replay_provider",
    "draft_single_pass",
    "estimate_cost_usd",
    "paced",
    "parse_draft",
    "participants_of",
    "prompt_version",
    "recording",
    "reply_offline",
    "reply_prompt_version",
    "requirement_blocks",
    "run_offline",
    "runs_pinning_sources",
    "trace_scope",
]
