"""A project's conversation with the agent: what people, the agent and the system said, in order.

Messages are append-only. A free message gets one read-only reply from a reply run; questions,
answers and run events are written by the run use cases that cause them (ADR 0010).
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from scopesteps.agent.domain.ids import MessageId, QuestionId, RunId
from scopesteps.agent.domain.run import Run
from scopesteps.identity.client import Actor, UserId
from scopesteps.kernel.errors import ConflictError, InvalidInputError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

# The same ceiling as a change request's text and a clarification answer: a message is a
# question or an instruction, not a document. Documents are uploaded as sources instead.
MAX_MESSAGE_CHARS = 2000


class MessageRole(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class MessageKind(StrEnum):
    """What a message is. The value is stored and is part of the API contract."""

    MESSAGE = "message"
    """A person's free message; the agent replies to it."""
    CHANGE_REQUEST = "change_request"
    """A person's request to change the baseline; a change run analyses it (ADR 0011)."""
    DISCUSS = "discuss"
    """A change a person wants to talk through before requesting it; the agent assesses it
    against the baseline in a read-only reply and changes nothing (ADR 0013 notes)."""
    REPLY = "reply"
    """The agent's read-only reply, made of claims with citations."""
    QUESTION = "question"
    """A clarification question the agent asked during a run."""
    ANSWER = "answer"
    SKIP = "skip"
    ANSWER_CHANGED = "answer_changed"
    EVENT = "event"
    ANALYSIS = "analysis"
    """The agent's analysis of a change request: claims with citations, like a reply."""


class ConversationEvent(StrEnum):
    """What an event message reports. Stored, and part of the API contract."""

    RUN_STARTED = "run.started"
    RUN_READY = "run.ready_for_review"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    REPLY_FAILED = "reply.failed"
    REPLY_CANCELLED = "reply.cancelled"
    CHANGE_READY = "change.ready_for_review"
    CHANGE_NOT_NEEDED = "change.no_change_needed"
    CHANGE_APPROVED = "change.approved"
    """An approver approved the request's candidate as the next baseline."""
    CHANGE_REJECTED = "change.rejected"
    """An approver rejected the request's candidate; the baseline is unchanged."""


ClaimBasis = Literal["cited", "agent"]
"""cited: backed by at least one resolving quote. agent: the agent's own words, with no evidence."""


@dataclass(frozen=True)
class CitedPassage:
    """A verbatim quote from a source paragraph or a recorded answer."""

    quote: str
    source_version_id: UUID | None = None
    block_id: UUID | None = None
    question_id: QuestionId | None = None


@dataclass(frozen=True)
class Claim:
    text: str
    basis: ClaimBasis
    citations: tuple[CitedPassage, ...] = ()


@dataclass(frozen=True)
class Message:
    id: MessageId
    project_id: ProjectId
    role: MessageRole
    kind: MessageKind
    text: str
    created_at: datetime
    author_id: UserId | None = None
    author_name: str | None = None
    """Copied when the message is written, so the thread reads the same after a rename."""
    run_id: RunId | None = None
    question_id: QuestionId | None = None
    event: ConversationEvent | None = None
    claims: tuple[Claim, ...] = ()
    change_request_id: UUID | None = None
    """For a change.approved or change.rejected event: the change request decided."""
    baseline_version: int | None = None
    """For a change.approved or change.rejected event: the baseline number after the decision."""


class InvalidMessageError(InvalidInputError):
    code = "MESSAGE_INVALID"


class AgentBusyError(ConflictError):
    """Other agent work is in progress in the project. Retryable once that work ends."""

    code = "AGENT_BUSY"
    retryable = True


def agent_busy(run: Run) -> AgentBusyError:
    """The refusal for new agent work while `run` is in progress."""
    work = {"reply": "a reply", "change": "a change request"}.get(run.mode, "a run")
    return AgentBusyError(
        f"The agent is working on {work}. Wait for it or stop it, then try again.",
        details={"run_id": str(run.id), "mode": run.mode, "status": run.status.value},
    )


class BaselineRequiredError(ConflictError):
    code = "BASELINE_REQUIRED"


class BaselineChangedError(ConflictError):
    """The change request names a baseline that is not the project's current one, or content
    that differs from it; nothing was stored."""

    code = "BASELINE_CHANGED"


def clean_message_text(text: str) -> str:
    """The text as stored: line endings normalized and outer whitespace removed."""
    cleaned = text.replace("\r\n", "\n").strip()
    if not cleaned:
        raise InvalidMessageError("Write a message before sending it.")
    if len(cleaned) > MAX_MESSAGE_CHARS:
        raise InvalidMessageError(
            f"A message can be at most {MAX_MESSAGE_CHARS} characters long.",
            details={"max_chars": MAX_MESSAGE_CHARS},
        )
    if not all(char in "\n\t" or char.isprintable() for char in cleaned):
        raise InvalidMessageError("A message cannot contain control or invisible characters.")
    return cleaned


def event_message(
    run_id: RunId,
    project_id: ProjectId,
    event: ConversationEvent,
    text: str,
    now: datetime,
    *,
    author: Actor | None = None,
) -> Message:
    """A system message about a run, attributed to the person whose action caused it."""
    return Message(
        id=MessageId(new_id()),
        project_id=project_id,
        role=MessageRole.SYSTEM,
        kind=MessageKind.EVENT,
        text=text,
        created_at=now,
        author_id=None if author is None else author.user_id,
        author_name=None if author is None else author.display_name,
        run_id=run_id,
        event=event,
    )


def change_outcome_message(
    run_id: RunId,
    project_id: ProjectId,
    *,
    change_request_id: UUID,
    number: int,
    approved: bool,
    baseline_version: int | None,
    decided_by: Actor,
    now: datetime,
) -> Message:
    """The event reporting an approver's decision on a change request's candidate."""
    if approved:
        text = f"CR-{number} was approved as baseline v{baseline_version}."
    elif baseline_version is None:
        text = f"CR-{number} was rejected; there is still no baseline."
    else:
        text = f"CR-{number} was rejected; the baseline stays v{baseline_version}."
    message = event_message(
        run_id,
        project_id,
        ConversationEvent.CHANGE_APPROVED if approved else ConversationEvent.CHANGE_REJECTED,
        text,
        now,
        author=decided_by,
    )
    return replace(message, change_request_id=change_request_id, baseline_version=baseline_version)


def question_message(
    run_id: RunId, project_id: ProjectId, question_id: QuestionId, text: str, now: datetime
) -> Message:
    return Message(
        id=MessageId(new_id()),
        project_id=project_id,
        role=MessageRole.AGENT,
        kind=MessageKind.QUESTION,
        text=text,
        created_at=now,
        run_id=run_id,
        question_id=question_id,
    )


def answer_message(
    run_id: RunId,
    project_id: ProjectId,
    question_id: QuestionId,
    answer: str | None,
    actor: Actor,
    now: datetime,
    *,
    changed: bool,
) -> Message:
    """A person's answer or skip; `changed` when it replaces an earlier one."""
    if changed:
        kind = MessageKind.ANSWER_CHANGED
    else:
        kind = MessageKind.SKIP if answer is None else MessageKind.ANSWER
    return Message(
        id=MessageId(new_id()),
        project_id=project_id,
        role=MessageRole.USER,
        kind=kind,
        text=answer or "",
        created_at=now,
        author_id=actor.user_id,
        author_name=actor.display_name,
        run_id=run_id,
        question_id=question_id,
    )


def reply_message(
    run_id: RunId,
    project_id: ProjectId,
    claims: Sequence[Claim],
    now: datetime,
    *,
    kind: MessageKind = MessageKind.REPLY,
) -> Message:
    """The agent's reply, or its analysis of a change request, as claims with citations."""
    return Message(
        id=MessageId(new_id()),
        project_id=project_id,
        role=MessageRole.AGENT,
        kind=kind,
        text="\n\n".join(claim.text for claim in claims),
        created_at=now,
        run_id=run_id,
        claims=tuple(claims),
    )
