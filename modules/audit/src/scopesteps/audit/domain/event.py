"""An audit event: one business action in a project, recorded once and never changed.

Events are shown to every project member, so they hold ids, names and counts only: never source
text, answers, credentials or model payloads.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from scopesteps.audit.domain.ids import AuditEventId
from scopesteps.identity.client import Actor, UserId
from scopesteps.kernel.errors import InvalidInputError
from scopesteps.projects.client import ProjectId

MAX_SUMMARY_CHARS = 200
MAX_ACTOR_NAME_CHARS = 200
MAX_SUBJECTS = 16


class ActorKind(StrEnum):
    USER = "user"
    AGENT = "agent"


class EventType(StrEnum):
    """Every action the activity log can show. The value is stored and is part of the API
    contract: add members, never rename or reuse one."""

    SOURCE_ADDED = "source.added"
    SOURCE_REMOVED = "source.removed"
    RUN_STARTED = "run.started"
    RUN_CANCELLED = "run.cancelled"
    RUN_FAILED = "run.failed"
    CLARIFICATION_REQUESTED = "clarification.requested"
    CLARIFICATION_ANSWERED = "clarification.answered"
    CLARIFICATION_SKIPPED = "clarification.skipped"
    CLARIFICATION_ANSWER_CHANGED = "clarification.answer_changed"
    MESSAGE_SENT = "message.sent"
    MESSAGE_REPLIED = "message.replied"
    BACKLOG_DRAFT_SAVED = "backlog.draft_saved"
    BACKLOG_ITEM_EDITED = "backlog.item_edited"
    BACKLOG_APPROVED = "backlog.approved"
    BACKLOG_REJECTED = "backlog.rejected"
    SUGGESTION_ACCEPTED = "suggestion.accepted"
    SUGGESTION_REJECTED = "suggestion.rejected"
    SCOPE_DECIDED = "scope.decided"
    CHANGE_REQUESTED = "change.requested"
    CHANGE_ANALYZED = "change.analyzed"
    CHANGE_APPROVED = "change.approved"
    CHANGE_REJECTED = "change.rejected"
    PERSON_CORRECTED = "person.corrected"
    PERSON_RIGHTS_CONFIRMED = "person.rights_confirmed"
    SPEAKERS_CONFIRMED = "speakers.confirmed"
    PROJECT_RENAMED = "project.renamed"
    USER_SIGNED_IN = "user.signed_in"
    USER_SIGNED_OUT = "user.signed_out"
    MEMBER_INVITED = "member.invited"
    INVITATION_LINK_CREATED = "invitation.link_created"
    INVITATION_EMAILED = "invitation.emailed"
    INVITATION_ACCEPTED = "invitation.accepted"
    INVITATION_CANCELLED = "invitation.cancelled"
    MEMBER_ROLES_CHANGED = "member.roles_changed"
    MEMBER_REMOVED = "member.removed"
    MEMBER_LEFT = "member.left"
    THREAD_STARTED = "thread.started"
    THREAD_RESOLVED = "thread.resolved"
    THREAD_REOPENED = "thread.reopened"


class SubjectKind(StrEnum):
    PROJECT = "project"
    USER = "user"
    SOURCE = "source"
    SOURCE_VERSION = "source_version"
    RUN = "run"
    QUESTION = "question"
    MESSAGE = "message"
    BACKLOG_VERSION = "backlog_version"
    ITEM = "item"
    CRITERION = "criterion"
    DECISION = "decision"
    CHANGE_SET = "change_set"
    CHANGE_REQUEST = "change_request"
    APPROVAL = "approval"
    PERSON = "person"
    INVITATION = "invitation"
    THREAD = "thread"


class InvalidCursorError(InvalidInputError):
    code = "INVALID_CURSOR"


@dataclass(frozen=True)
class Subject:
    """Something an event concerns, by id. The owning module resolves it to content, under its
    own access rules."""

    kind: SubjectKind
    id: UUID


@dataclass(frozen=True)
class AuditActor:
    """Who acted. The name is copied at the time of the action, so the log reads the same after a
    user is renamed."""

    kind: ActorKind
    user_id: UserId | None = None
    display_name: str | None = None

    def __post_init__(self) -> None:
        if (self.kind == ActorKind.USER) != (self.user_id is not None):
            raise ValueError("A user actor has a user id; the agent has none")
        if (self.user_id is None) != (self.display_name is None):
            raise ValueError("An actor has a display name exactly when it is a user")
        if self.display_name is not None:
            _require_short_line(self.display_name, MAX_ACTOR_NAME_CHARS, "actor name")

    @classmethod
    def user(cls, actor: Actor) -> Self:
        return cls(ActorKind.USER, actor.user_id, actor.display_name)

    @classmethod
    def agent(cls) -> Self:
        return cls(ActorKind.AGENT)


@dataclass(frozen=True)
class AuditEvent:
    id: AuditEventId
    project_id: ProjectId
    actor: AuditActor
    type: EventType
    subjects: tuple[Subject, ...]
    summary: str
    """One line a member can read, built from names, numbers and counts."""
    occurred_at: datetime

    def __post_init__(self) -> None:
        _require_short_line(self.summary, MAX_SUMMARY_CHARS, "summary")
        if not 1 <= len(self.subjects) <= MAX_SUBJECTS:
            raise ValueError(f"An audit event concerns 1 to {MAX_SUBJECTS} subjects")
        if self.occurred_at.tzinfo is None:
            raise ValueError("An audit event's time is timezone-aware")


@dataclass(frozen=True)
class FeedCursor:
    """The position after an event in the newest-first feed."""

    occurred_at: datetime
    id: AuditEventId


def _require_short_line(text: str, max_chars: int, what: str) -> None:
    # Documents and answers are long or multi-line; refusing both keeps pasted content out even
    # when a caller builds a summary carelessly.
    if not text.strip() or len(text) > max_chars or not text.isprintable():
        raise ValueError(f"An audit event's {what} is one printable line of 1 to {max_chars} chars")
