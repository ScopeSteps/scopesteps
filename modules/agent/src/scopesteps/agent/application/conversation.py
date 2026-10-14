"""Conversation use cases: post a message and read the thread.

A free message starts a reply run: a durable run in `reply` mode that `advance` drives through
one read-only step under the same lease, limits and budgets as any run (ADR 0005, ADR 0010).
"""

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from scopesteps.agent.application.ports import MessageCursor, ProjectContext, Receipt, RunStore
from scopesteps.agent.application.replying import REPLY_PROMPT_VERSION, REPLY_SCHEMA_VERSION
from scopesteps.agent.application.runs import (
    AgentRuntime,
    IdempotencyKeyReusedError,
    ModelNotConfiguredError,
)
from scopesteps.agent.domain.conversation import (
    AgentBusyError,
    BaselineRequiredError,
    Message,
    MessageKind,
    MessageRole,
    clean_message_text,
)
from scopesteps.agent.domain.ids import MessageId, RunId
from scopesteps.agent.domain.run import (
    ADVANCEABLE,
    Question,
    Run,
    RunInputs,
    RunStage,
    RunStatus,
)
from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.identity.client import ProjectAccess, Role
from scopesteps.kernel.errors import ConflictError, FeatureNotImplementedError, InvalidInputError
from scopesteps.kernel.ids import new_id

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
POST_OPERATION = "message"


class InvalidCursorError(InvalidInputError):
    code = "INVALID_CURSOR"


@dataclass(frozen=True)
class PostMessage:
    idempotency_key: str
    text: str
    kind: Literal["message", "change_request"]


@dataclass(frozen=True)
class PostedMessage:
    message: Message
    run: Run
    """The reply run to advance. Its status says whether the reply is still to come."""


@dataclass(frozen=True)
class ConversationPage:
    messages: tuple[Message, ...]
    next_cursor: str | None
    """Pass it back to read the next, older page. None on the last page."""
    questions: dict[UUID, Question]
    """The current state of every question the page's messages refer to."""
    active_run: Run | None
    """The newest run that is created, running or waiting for answers, if any."""


def post_message(
    store: RunStore,
    audit: AuditRecorder,
    context: ProjectContext,
    runtime: AgentRuntime,
    access: ProjectAccess,
    command: PostMessage,
    now: datetime,
) -> PostedMessage:
    """Store the message and create the reply run that answers it, in one transaction.

    Refused with 409 `AGENT_BUSY` while a run in the project is created or running. A change
    request hands off to change analysis, which is not built yet: it is checked and refused with
    501, storing nothing. A retry with the same Idempotency-Key returns what the first stored.
    """
    access.require_role(Role.EDITOR)
    text = clean_message_text(command.text)
    digest = _fingerprint([command.kind, text, str(access.project_id)])
    receipt = store.find_receipt(access.actor.user_id, command.idempotency_key)
    if receipt is not None:
        if receipt.operation != POST_OPERATION or receipt.fingerprint != digest:
            raise IdempotencyKeyReusedError(
                "This Idempotency-Key was already used for another request"
            )
        return _replayed(store, receipt.run_id)
    if command.kind == "change_request":
        if not context.has_baseline(access.project_id):
            raise BaselineRequiredError(
                "A change can be requested once a baseline has been approved."
            )
        # The hand-off point to change analysis: it will create a change run against the
        # current baseline here. Until then nothing is stored, so the request can be resent.
        raise FeatureNotImplementedError("Change requests")
    busy = store.active_run(access.project_id)
    if busy is not None and busy.status in ADVANCEABLE:
        raise _busy(busy)
    primary = runtime.primary
    if primary is None:
        raise ModelNotConfiguredError("No model provider is configured (MODEL_PROVIDER)")
    # Two messages sent at once both see no work in progress; only one may take the turn.
    if not store.claim_turn(access.project_id):
        raise AgentBusyError("Another message was sent at the same time. Wait for its reply.")
    served, fallback_reason = primary, None
    if runtime.fallback is not None and runtime.breaker.is_open():
        served, fallback_reason = runtime.fallback, "primary_circuit_open"
    run = Run(
        id=RunId(new_id()),
        project_id=access.project_id,
        mode="reply",
        status=RunStatus.CREATED,
        stage=RunStage.REPLY,
        revision=1,
        inputs=RunInputs(
            source_version_ids=tuple(context.current_source_versions(access.project_id)),
            provider=served.provider_name,
            model_id=served.model_id,
            fallback_reason=fallback_reason,
            prompt_version=REPLY_PROMPT_VERSION,
            schema_version=REPLY_SCHEMA_VERSION,
            limits=runtime.limits,
            max_clarification_rounds=0,
        ),
        created_by=access.actor.user_id,
        created_at=now,
        updated_at=now,
    )
    message = Message(
        id=MessageId(new_id()),
        project_id=access.project_id,
        role=MessageRole.USER,
        kind=MessageKind.MESSAGE,
        text=text,
        created_at=now,
        author_id=access.actor.user_id,
        author_name=access.actor.display_name,
        run_id=run.id,
    )
    store.add_run(run)
    store.add_messages([message])
    store.add_receipt(
        Receipt(
            actor_id=access.actor.user_id,
            idempotency_key=command.idempotency_key,
            operation=POST_OPERATION,
            run_id=run.id,
            fingerprint=digest,
            created_at=now,
        )
    )
    audit.record(
        project_id=access.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.MESSAGE_SENT,
        subjects=(Subject(SubjectKind.MESSAGE, message.id), Subject(SubjectKind.RUN, run.id)),
        summary="Sent a message to the agent",
        occurred_at=now,
    )
    store.commit()
    return PostedMessage(message, run)


def list_conversation(
    store: RunStore, access: ProjectAccess, *, limit: int, cursor: str | None
) -> ConversationPage:
    """One page of the thread, newest first. Every member sees the same conversation."""
    access.require_member()
    before = None if cursor is None else decode_cursor(cursor)
    # One extra row tells whether an older page exists without a count query.
    rows = store.newest_messages(access.project_id, before=before, limit=limit + 1)
    page = rows[:limit]
    question_ids = list(dict.fromkeys(m.question_id for m in page if m.question_id is not None))
    return ConversationPage(
        messages=tuple(page),
        next_cursor=encode_cursor(MessageCursor(page[-1].created_at, page[-1].id))
        if len(rows) > limit
        else None,
        questions={q.id: q for q in store.questions_by_id(question_ids)},
        active_run=store.active_run(access.project_id),
    )


def encode_cursor(cursor: MessageCursor) -> str:
    raw = f"{cursor.created_at.isoformat()}|{cursor.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(value: str) -> MessageCursor:
    try:
        created_at, _, message_id = base64.urlsafe_b64decode(value).decode().partition("|")
        cursor = MessageCursor(datetime.fromisoformat(created_at), MessageId(UUID(message_id)))
    except (ValueError, binascii.Error) as error:
        raise InvalidCursorError("The cursor is not one this conversation returned") from error
    if cursor.created_at.tzinfo is None:
        raise InvalidCursorError("The cursor is not one this conversation returned")
    return cursor


def _busy(run: Run) -> AgentBusyError:
    work = "a reply" if run.mode == "reply" else "a run"
    return AgentBusyError(
        f"The agent is working on {work}. Wait for it or stop it, then send your message.",
        details={"run_id": str(run.id), "mode": run.mode, "status": run.status.value},
    )


def _replayed(store: RunStore, run_id: RunId) -> PostedMessage:
    run = store.get_run(run_id)
    message = next((m for m in store.run_messages(run_id) if m.kind == MessageKind.MESSAGE), None)
    if run is None or message is None:
        raise ConflictError("The request with this Idempotency-Key did not store a message")
    return PostedMessage(message, run)


def _fingerprint(parts: list[str]) -> str:
    return hashlib.sha256(json.dumps([POST_OPERATION, *parts]).encode()).hexdigest()
