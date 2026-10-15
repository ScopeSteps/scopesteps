from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, BigInteger, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from scopesteps.agent.domain.conversation import ConversationEvent, MessageKind, MessageRole
from scopesteps.agent.domain.run import QuestionStatus, RunStage, RunStatus
from scopesteps.infrastructure.database import Base, UtcDateTime


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


def _enum(enum_class: type[StrEnum]) -> Enum:
    return Enum(enum_class, native_enum=False, length=32, values_callable=_enum_values)


class RunRecord(Base):
    __tablename__ = "agent_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"), index=True)
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus))
    stage: Mapped[RunStage] = mapped_column(_enum(RunStage))
    # Compare-and-set guard: every write checks the revision it read, then increments it.
    revision: Mapped[int]
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_turns: Mapped[int]
    tool_calls: Mapped[int]
    total_tokens: Mapped[int]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    thinking_tokens: Mapped[int]
    cost_microusd: Mapped[int] = mapped_column(BigInteger)
    clarification_rounds: Mapped[int]
    # Conversation replayed to the model. Holds source text and model output, so it is never
    # logged, traced or returned by the API.
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, deferred=True)
    pending_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, deferred=True)
    draft: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    problems: Mapped[list[str]] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_retryable: Mapped[bool | None]
    lease_token: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class RunStepRecord(Base):
    """Append-only: one row per model call or tool execution, with no prompt or output text."""

    __tablename__ = "agent_run_steps"
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.id"))
    sequence: Mapped[int]
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64))
    stage: Mapped[RunStage] = mapped_column(_enum(RunStage))
    provider: Mapped[str] = mapped_column(String(64))
    model_id: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(128))
    schema_version: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int]
    repair: Mapped[str] = mapped_column(String(16))
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    thinking_tokens: Mapped[int]
    latency_ms: Mapped[int]
    finish_reason: Mapped[str] = mapped_column(String(32))
    tool_calls: Mapped[int]
    error_kind: Mapped[str | None] = mapped_column(String(32))
    cost_microusd: Mapped[int | None] = mapped_column(BigInteger)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class QuestionRecord(Base):
    __tablename__ = "agent_run_questions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    round: Mapped[int]
    call_id: Mapped[str] = mapped_column(String(128))
    subject: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text)
    block_labels: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[QuestionStatus] = mapped_column(_enum(QuestionStatus))
    answer: Mapped[str | None] = mapped_column(Text)
    answer_label: Mapped[str | None] = mapped_column(String(16))
    answered_by: Mapped[UUID | None] = mapped_column(ForeignKey("identity_users.id"))
    answered_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class RequestReceiptRecord(Base):
    __tablename__ = "agent_request_receipts"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    operation: Mapped[str] = mapped_column(String(16))
    run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.id"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class MessageRecord(Base):
    """Append-only: one row per message in a project's conversation, ordered by time then id."""

    __tablename__ = "agent_messages"
    __table_args__ = (Index("ix_agent_messages_project_order", "project_id", "created_at", "id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"))
    role: Mapped[MessageRole] = mapped_column(_enum(MessageRole))
    kind: Mapped[MessageKind] = mapped_column(_enum(MessageKind))
    # Holds what people wrote and the agent replied, so it is never logged or traced.
    text: Mapped[str] = mapped_column(Text)
    author_id: Mapped[UUID | None] = mapped_column(ForeignKey("identity_users.id"))
    author_name: Mapped[str | None] = mapped_column(String(200))
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    question_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_run_questions.id"))
    event: Mapped[ConversationEvent | None] = mapped_column(_enum(ConversationEvent))
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    # Not a foreign key: change requests belong to the change_control module.
    change_request_id: Mapped[UUID | None]
    baseline_version: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class ConversationTurnRecord(Base):
    """One row per project that has started work from the conversation. Its revision is
    compare-and-set by every message that starts work, so two sent at once cannot both."""

    __tablename__ = "agent_conversation_turns"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"), primary_key=True)
    revision: Mapped[int]
