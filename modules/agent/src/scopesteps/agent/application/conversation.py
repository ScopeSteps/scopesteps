"""Conversation use cases: post a message and read the thread.

A free message starts a reply run: a durable run in `reply` mode that `advance` drives through
one read-only step under the same lease, limits and budgets as any run (ADR 0005, ADR 0010).
"""

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from scopesteps.agent.application.change_requests import SubmitChange, submit_change_request
from scopesteps.agent.application.ports import (
    ChangeRequests,
    MessageCursor,
    ProjectContext,
    Receipt,
    RunStore,
)
from scopesteps.agent.application.replying import (
    DISCUSS_PROMPT_VERSION,
    DISCUSS_REPLY,
    REPLY_PROMPT_VERSION,
    REPLY_SCHEMA_VERSION,
    REPLY_SCHEMAS,
)
from scopesteps.agent.application.runs import (
    AgentRuntime,
    IdempotencyKeyReusedError,
    ModelNotConfiguredError,
)
from scopesteps.agent.domain.conversation import (
    AgentBusyError,
    BaselineRequiredError,
    InvalidMessageError,
    Message,
    MessageKind,
    MessageRole,
    agent_busy,
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
from scopesteps.agent.domain.suggestion import Suggestion, SuggestionChangedError
from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.identity.client import ProjectAccess, Role
from scopesteps.kernel.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
)
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
    kind: Literal["message", "discuss", "change_request"]
    base_version_id: UUID | None = None
    """For a change request: the baseline the requester saw. Required with the hash."""
    base_content_hash: str | None = None


@dataclass(frozen=True)
class PostedMessage:
    message: Message
    run: Run
    """The reply run, or for a change request the change run, to advance."""


@dataclass(frozen=True)
class ConversationPage:
    messages: tuple[Message, ...]
    next_cursor: str | None
    """Pass it back to read the next, older page. None on the last page."""
    questions: dict[UUID, Question]
    """The current state of every question the page's messages refer to."""
    active_run: Run | None
    """The newest run that is created, running or waiting for answers, if any."""
    suggestions: dict[MessageId, Suggestion] = field(default_factory=dict[MessageId, Suggestion])
    """The suggestions the page's replies made, by reply message (ADR 0013)."""


def post_message(
    store: RunStore,
    audit: AuditRecorder,
    context: ProjectContext,
    requests: ChangeRequests,
    runtime: AgentRuntime,
    access: ProjectAccess,
    command: PostMessage,
    now: datetime,
) -> PostedMessage:
    """Store the message and create the run that answers it, in one transaction.

    A free message gets a reply run. A discussion gets a reply run that weighs the proposed
    change against the approved baseline and changes nothing; it needs a baseline (409
    `BASELINE_REQUIRED`). A change request gets a change run against the baseline the requester
    saw (ADR 0011). Refused with 409 `AGENT_BUSY` while a run in the project is created or
    running. A retry with the same Idempotency-Key returns what the first stored.
    """
    access.require_role(Role.EDITOR)
    text = clean_message_text(command.text)
    base = [str(command.base_version_id), command.base_content_hash or ""]
    digest = _fingerprint(
        [command.kind, text, str(access.project_id), *(base if command.kind != "message" else [])]
    )
    receipt = store.find_receipt(access.actor.user_id, command.idempotency_key)
    if receipt is not None:
        if receipt.operation != POST_OPERATION or receipt.fingerprint != digest:
            raise IdempotencyKeyReusedError(
                "This Idempotency-Key was already used for another request"
            )
        return _replayed(store, receipt.run_id)
    if command.kind == "change_request":
        if command.base_version_id is None or command.base_content_hash is None:
            raise InvalidMessageError(
                "A change request names the baseline it was made against "
                "(base_version_id and base_content_hash)."
            )
        submitted = submit_change_request(
            store,
            audit,
            context,
            requests,
            runtime,
            access,
            SubmitChange(
                idempotency_key=command.idempotency_key,
                text=text,
                base_version_id=command.base_version_id,
                base_content_hash=command.base_content_hash,
                operation=POST_OPERATION,
                fingerprint=digest,
            ),
            now,
        )
        return PostedMessage(submitted.message, submitted.run)
    discuss = command.kind == "discuss"
    if discuss and not context.has_baseline(access.project_id):
        raise BaselineRequiredError(
            "A change can be talked through once a baseline is approved. Ask a question instead."
        )
    busy = store.active_run(access.project_id)
    if busy is not None and busy.status in ADVANCEABLE:
        raise agent_busy(busy)
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
            prompt_version=DISCUSS_PROMPT_VERSION if discuss else REPLY_PROMPT_VERSION,
            schema_version=REPLY_SCHEMAS[DISCUSS_REPLY] if discuss else REPLY_SCHEMA_VERSION,
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
        kind=MessageKind.DISCUSS if discuss else MessageKind.MESSAGE,
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
        summary="Asked the agent to talk a change through"
        if discuss
        else "Sent a message to the agent",
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
        suggestions=store.suggestions_for([m.id for m in page if m.kind == MessageKind.REPLY]),
    )


@dataclass(frozen=True)
class DecideSuggestion:
    message_id: MessageId
    status: Literal["accepted", "dismissed"]
    expected_revision: int


def decide_suggestion(
    store: RunStore, access: ProjectAccess, command: DecideSuggestion, now: datetime
) -> Suggestion:
    """Record that a person accepted or dismissed a reply's suggestion (ADR 0013).

    Accepting runs nothing: the client has already called the existing endpoint, which checked
    the action itself. Any role that may act on the project (editor or approver) records it.
    Recording the status it already has returns it unchanged; deciding it the other way is
    refused, as is a stale `expected_revision`. Idempotent by state, so no receipt is kept.
    """
    access.require_member()
    if not access.roles & {Role.EDITOR, Role.APPROVER}:
        raise PermissionDeniedError("Only an editor or approver can act on a suggestion")
    suggestion = store.suggestions_for([command.message_id]).get(command.message_id)
    # A message of another project is reported exactly like a missing one.
    if suggestion is None or suggestion.project_id != access.project_id:
        raise NotFoundError("Suggestion not found")
    if suggestion.status == command.status:
        return suggestion
    if suggestion.revision != command.expected_revision:
        raise SuggestionChangedError(
            "This suggestion changed since you loaded it. Reload the conversation.",
            details={"current_revision": suggestion.revision, "status": suggestion.status},
        )
    decided = suggestion.decided(command.status, access.actor.user_id, now)
    if not store.save_suggestion(decided, expected_revision=suggestion.revision):
        raise SuggestionChangedError(
            "This suggestion changed while saving. Reload the conversation.",
            details={"current_revision": suggestion.revision + 1},
        )
    store.commit()
    return decided


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


def _replayed(store: RunStore, run_id: RunId) -> PostedMessage:
    run = store.get_run(run_id)
    sent = {MessageKind.MESSAGE, MessageKind.CHANGE_REQUEST}
    message = next((m for m in store.run_messages(run_id) if m.kind in sent), None)
    if run is None or message is None:
        raise ConflictError("The request with this Idempotency-Key did not store a message")
    return PostedMessage(message, run)


def _fingerprint(parts: list[str]) -> str:
    return hashlib.sha256(json.dumps([POST_OPERATION, *parts]).encode()).hexdigest()
