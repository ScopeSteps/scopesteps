"""An agent run: a durable, bounded state machine. Code decides every transition; the model only
proposes tool calls and drafts."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from scopesteps.agent.domain.budget import RunCounters, RunLimits
from scopesteps.agent.domain.ids import QuestionId, RunId, StepId
from scopesteps.agent.domain.model import ModelResult, ToolResult, Turn
from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import ConflictError
from scopesteps.projects.client import ProjectId


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_FOR_INPUT = "waiting_for_input"
    READY_FOR_REVIEW = "ready_for_review"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    """A reply run that answered. Reply runs never become ready_for_review."""


ADVANCEABLE = frozenset({RunStatus.CREATED, RunStatus.RUNNING})
TERMINAL = frozenset(
    {RunStatus.READY_FOR_REVIEW, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.COMPLETED}
)
IN_PROGRESS = frozenset({*ADVANCEABLE, RunStatus.WAITING_FOR_INPUT})

RunMode = Literal["initial", "reply"]
"""initial drafts a backlog; reply answers one conversation message, read-only (ADR 0010)."""


class RunStage(StrEnum):
    """What the next step does. Explore may look up sources or ask the reviewer; draft makes the
    typed draft with its one repair, exactly as the single-pass baseline does."""

    EXPLORE = "explore"
    DRAFT = "draft"
    REPLY = "reply"


class QuestionStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    SKIPPED = "skipped"


class RunBusyError(ConflictError):
    """Another request holds the run's lease and is mid-step."""

    code = "RUN_BUSY"
    retryable = True


class RunChangedError(ConflictError):
    """The run changed between reading and writing it; nothing from this request was saved."""

    code = "RUN_CHANGED"
    retryable = True


class RunStateError(ConflictError):
    code = "RUN_STATE_INVALID"


class AnswerLockedError(ConflictError):
    """The answer is part of an approved backlog version, which never changes."""

    code = "ANSWER_LOCKED"


@dataclass(frozen=True)
class RunError:
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class Lease:
    """Held by one advance request while it calls the model outside any transaction. An expired
    lease belongs to a request that died or overran; the next advance may take the run over."""

    token: UUID
    expires_at: datetime


@dataclass(frozen=True)
class RunInputs:
    """Pinned when the run is created, so later setting or source changes cannot alter it."""

    source_version_ids: tuple[UUID, ...]
    provider: str
    model_id: str
    prompt_version: str
    schema_version: str
    limits: RunLimits
    max_clarification_rounds: int
    fallback_reason: str | None = None
    """Set when the run uses the backup provider, with why (ADR 0006)."""


@dataclass(frozen=True)
class TokenTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cost_microusd: int = 0
    """Estimated cost at paid rates in millionths of a US dollar, exact in every database."""


@dataclass(frozen=True)
class Run:
    id: RunId
    project_id: ProjectId
    mode: RunMode
    status: RunStatus
    stage: RunStage
    revision: int
    inputs: RunInputs
    created_by: UserId
    created_at: datetime
    updated_at: datetime
    counters: RunCounters = field(default_factory=RunCounters)
    totals: TokenTotals = field(default_factory=TokenTotals)
    clarification_rounds: int = 0
    history: tuple[Turn, ...] = ()
    """Conversation replayed to the model on each step. Stored, never returned by the API."""
    pending_results: tuple[ToolResult, ...] = ()
    """Results of tools called alongside request_clarification, sent with the answers."""
    draft: dict[str, object] | None = None
    problems: tuple[str, ...] = ()
    error: RunError | None = None
    lease: Lease | None = None

    def lease_is_active(self, now: datetime) -> bool:
        return self.lease is not None and self.lease.expires_at > now


@dataclass(frozen=True)
class Question:
    """A clarification question the agent asked. Answers become citable blocks (A1, A2, ...)."""

    id: QuestionId
    run_id: RunId
    round: int
    call_id: str
    """The request_clarification call whose result the answers become."""
    subject: str
    text: str
    why_it_matters: str
    block_labels: tuple[str, ...]
    status: QuestionStatus = QuestionStatus.OPEN
    answer: str | None = None
    answer_label: str | None = None
    """The block id the answer or the open decision is cited by in later prompts."""
    answered_by: UserId | None = None
    answered_at: datetime | None = None


StepKind = Literal["model_call", "tool", "event"]


@dataclass(frozen=True)
class RunStep:
    """One model call or tool execution. Append-only; never holds prompt, source or output text."""

    id: StepId
    run_id: RunId
    kind: StepKind
    name: str
    stage: RunStage
    created_at: datetime
    provider: str = ""
    model_id: str = ""
    prompt_version: str = ""
    schema_version: str = ""
    attempt: int = 1
    repair: str = "none"
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    latency_ms: int = 0
    finish_reason: str = ""
    tool_calls: int = 0
    error_kind: str | None = None
    cost_microusd: int | None = None
    detail: dict[str, object] = field(default_factory=dict[str, object])
    """Counts and codes only, for example the number of problems validate_backlog found."""
    sequence: int = 0
    """Position within the run, assigned when the step is stored."""


def with_call(run: Run, result: ModelResult, cost_microusd: int | None) -> Run:
    """Counters and totals after a successful model call."""
    totals = run.totals
    return replace(
        run,
        counters=run.counters.after_call(result),
        totals=TokenTotals(
            input_tokens=totals.input_tokens + result.usage.input_tokens,
            output_tokens=totals.output_tokens + result.usage.output_tokens,
            thinking_tokens=totals.thinking_tokens + result.usage.thinking_tokens,
            cost_microusd=totals.cost_microusd + (cost_microusd or 0),
        ),
    )
