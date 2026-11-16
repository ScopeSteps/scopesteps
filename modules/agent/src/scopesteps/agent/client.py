from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
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
    DRAFT_PROMPTS,
    PROMPT_CHECKS,
    PROMPT_SCHEMAS,
    STEPWISE_PROMPTS,
    DraftOutcome,
    PromptName,
    draft_single_pass,
    prompt_version,
)
from scopesteps.agent.application.offline import (
    Answerer,
    EarlierMessage,
    OfflineChange,
    OfflineReply,
    OfflineRun,
    OfflineTasks,
    RecordedAnswer,
    analyze_change_offline,
    reply_offline,
    run_offline,
    suggest_tasks_offline,
)
from scopesteps.agent.application.outcomes import OutcomeSink, log_outcome
from scopesteps.agent.application.ports import ModelProvider, ModelRouting, Passage, StepModel
from scopesteps.agent.application.replying import (
    CONVERSATION_REPLY,
    DISCUSS_REPLIES,
    DISCUSS_REPLY,
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
from scopesteps.agent.application.stepwise import (
    STEPWISE_PROMPT,
    DraftInputs,
    StepwiseProgress,
    draft_in_steps,
)
from scopesteps.agent.application.suggesting import TASKS_PROMPT_VERSION, TASKS_PROMPTS
from scopesteps.agent.application.tracing import trace_scope
from scopesteps.agent.domain.budget import MICROUSD_PER_USD, RunLimits
from scopesteps.agent.domain.conversation import CitedPassage, Claim
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
from scopesteps.agent.domain.profiles import InvalidProfileError, ModelProfile, Step, StepBinding
from scopesteps.agent.domain.providers import REPLAY_PROVIDER
from scopesteps.agent.domain.run import Question, QuestionStatus, RunStatus
from scopesteps.agent.infrastructure.profiles import load_profile, profile_ids
from scopesteps.agent.infrastructure.providers.anthropic import PROVIDER as ANTHROPIC_PROVIDER
from scopesteps.agent.infrastructure.providers.anthropic_messages import AnthropicMessagesProvider
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.agent.infrastructure.providers.replay import RecordingProvider, ReplayProvider
from scopesteps.agent.infrastructure.providers.traced import TraceSink, log_sink
from scopesteps.agent.infrastructure.repository import SqlRunRepository
from scopesteps.agent.infrastructure.routing import (
    ModelRouter,
    RequestLimit,
    catalog_request_limit,
)
from scopesteps.agent.infrastructure.telemetry import (
    FINISH_REASON_LABEL,
    OtlpConfig,
    Telemetry,
    otlp_telemetry,
)
from scopesteps.kernel.limits import MAX_MESSAGE_CHARS
from scopesteps.projects.client import ProjectId

FAKE_PROVIDER = "fake"
"""The provider of the `fake` profile: scripted results, for tests only."""


def create_model_router(
    adapters: Mapping[str, ModelProvider],
    *,
    trace_sink: TraceSink = log_sink,
    request_limit: RequestLimit | None = None,
) -> ModelRouter:
    """The one place adapters are put behind the router, each traced (content-free, OpenTelemetry
    GenAI attribute names) to `trace_sink`. There is no fallback provider (ADR 0032)."""
    if request_limit is None:
        return ModelRouter(adapters, trace_sink=trace_sink)
    return ModelRouter(adapters, trace_sink=trace_sink, request_limit=request_limit)


def create_anthropic_adapter(api_key: str) -> ModelProvider:
    """The Claude adapter (ADR 0032): one instance serves every Claude model a profile names."""
    return AnthropicMessagesProvider(api_key=api_key)


def scripted_router(provider: ModelProvider) -> ModelRouting:
    """A router serving the `fake` profile from `provider`: Claude's model names on scripted
    results, for tests of the offline runs and the evaluations."""
    return create_model_router({FAKE_PROVIDER: provider})


def unscripted_provider() -> ModelProvider:
    """The `fake` provider before a test scripts it: every call fails the test."""
    return ScriptedProvider(())


def create_replay_adapter(path: Path) -> tuple[ModelProvider, str]:
    """An adapter that replays a recording, and the model it was recorded with. Runs made with
    it are pinned to a profile on the provider `REPLAY_PROVIDER`, never a live one."""
    replay = ReplayProvider.from_file(path)
    return replay, replay.model_id


def recording(
    provider: ModelProvider, path: Path, *, provider_name: str, label: str
) -> ModelProvider:
    """Wrap a live adapter so each successful result is also written to a replay file. `label`
    names what the recording was made with (the profile id) for the replay banner."""
    return RecordingProvider(provider, path, provider=provider_name, model_id=label)


def runs_pinning_sources(
    session: Session, project_id: ProjectId, source_version_ids: Collection[UUID]
) -> list[RunId]:
    """The project's runs, in any status, that pinned any of the source versions. Performs no
    access check."""
    return SqlRunRepository(session).runs_pinning(project_id, source_version_ids)


def open_question_counts(
    session: Session, project_ids: Collection[ProjectId]
) -> dict[ProjectId, int]:
    """For each project given, the clarification questions waiting for an answer in its runs
    that wait for input, in one query; projects with none are absent. Performs no access check."""
    return SqlRunRepository(session).open_question_counts(project_ids)


@dataclass(frozen=True)
class OpenQuestion:
    id: QuestionId
    subject: str


def open_questions(session: Session, project_id: ProjectId) -> list[OpenQuestion]:
    """The clarification questions waiting for an answer in the project's runs that wait for
    input, the same ones `open_question_counts` counts. Performs no access check."""
    return [
        OpenQuestion(QuestionId(question_id), subject)
        for question_id, subject in SqlRunRepository(session).open_questions(project_id)
    ]


@dataclass(frozen=True)
class CoverageCounts:
    confirmed: int
    """Confirmed statements in the draft."""
    covered: int
    """Confirmed statements at least one story covers (ADR 0028)."""


def draft_coverage(session: Session, run_id: UUID) -> CoverageCounts | None:
    """How much of what the sources confirm the draft of an initial run covers, counted as the
    run's own coverage panel counts it; None for a change run, a run with no draft, or a draft
    from before stories listed what they cover. Performs no access check."""
    run = SqlRunRepository(session).get_run(RunId(run_id))
    if run is None or run.mode != "initial" or run.draft is None:
        return None
    draft = parse_draft(run.draft)
    if isinstance(draft, DraftBacklogV1):
        return None
    covered = {ref for item in draft.items if item.kind == "story" for ref in item.covers}
    confirmed = [s for s in draft.statements if s.kind == "confirmed"]
    return CoverageCounts(len(confirmed), sum(s.id in covered for s in confirmed))


__all__ = [
    "AGENT_EXPLORE",
    "AGENT_PROMPT_VERSION",
    "ANTHROPIC_PROVIDER",
    "CHANGE_PROMPT_VERSION",
    "CHANGE_REQUEST_KIND",
    "CHANGE_RUN",
    "CHANGE_SCHEMA_VERSION",
    "CONVERSATION_REPLY",
    "DEFAULT_PROMPT",
    "DISCUSS_REPLIES",
    "DISCUSS_REPLY",
    "DRAFT_PROMPTS",
    "DRAFT_PROMPT_VERSION",
    "DRAFT_SCHEMA_VERSION",
    "FAKE_PROVIDER",
    "FINISH_REASON_LABEL",
    "MAX_MESSAGE_CHARS",
    "MICROUSD_PER_USD",
    "PRICES_CHECKED",
    "PROMPT_CHECKS",
    "PROMPT_SCHEMAS",
    "REPLAY_PROVIDER",
    "REPLY_PROMPT_VERSION",
    "REPLY_SCHEMAS",
    "REPLY_SCHEMA_VERSION",
    "STEPWISE_PROMPT",
    "STEPWISE_PROMPTS",
    "TASKS_PROMPTS",
    "TASKS_PROMPT_VERSION",
    "USER_STORY",
    "AgentRuntime",
    "Answerer",
    "AnyDraft",
    "BaselineLabels",
    "ChangeName",
    "ChangeResult",
    "ChangeSetOutput",
    "CitedPassage",
    "Claim",
    "CoverageCounts",
    "DraftBacklog",
    "DraftBacklogV1",
    "DraftBacklogV4",
    "DraftBacklogV5",
    "DraftInputs",
    "DraftOutcome",
    "DraftPerson",
    "DraftPersonV5",
    "EarlierMessage",
    "ExploreName",
    "InvalidProfileError",
    "MessageId",
    "ModelProfile",
    "ModelProvider",
    "ModelProviderError",
    "ModelRequest",
    "ModelResult",
    "ModelRouter",
    "ModelRouting",
    "ModelTurn",
    "OfflineChange",
    "OfflineReply",
    "OfflineRun",
    "OfflineTasks",
    "OpenQuestion",
    "OtlpConfig",
    "OutcomeSink",
    "Participants",
    "Passage",
    "PromptName",
    "Question",
    "QuestionId",
    "QuestionStatus",
    "RecordedAnswer",
    "ReplyName",
    "RunId",
    "RunLimits",
    "RunStatus",
    "SourceBlockInput",
    "SpeakerNote",
    "Step",
    "StepBinding",
    "StepModel",
    "StepwiseProgress",
    "Telemetry",
    "ToolCall",
    "TraceSink",
    "Usage",
    "UserMessage",
    "analyze_change_offline",
    "catalog_request_limit",
    "change_prompt_version",
    "change_schema_version",
    "check_draft",
    "create_anthropic_adapter",
    "create_model_router",
    "create_replay_adapter",
    "draft_coverage",
    "draft_in_steps",
    "draft_single_pass",
    "estimate_cost_usd",
    "load_profile",
    "log_outcome",
    "log_sink",
    "open_question_counts",
    "open_questions",
    "otlp_telemetry",
    "parse_draft",
    "participants_of",
    "profile_ids",
    "prompt_version",
    "recording",
    "reply_offline",
    "reply_prompt_version",
    "requirement_blocks",
    "run_offline",
    "runs_pinning_sources",
    "scripted_router",
    "suggest_tasks_offline",
    "trace_scope",
    "unscripted_provider",
]
