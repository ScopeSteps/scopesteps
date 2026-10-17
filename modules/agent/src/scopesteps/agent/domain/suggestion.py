"""A next step a reply suggests, which a person may take with one click (ADR 0013).

A suggestion is something a person already does in the app: submit a change request, answer an
open decision, or start a draft run. Storing one runs nothing. Accepting it means the person's
client called the existing endpoint, which repeats every check; the status only records what
happened, so the thread shows it and the next reply can take it into account.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal
from uuid import UUID

from scopesteps.agent.domain.ids import MessageId
from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import ConflictError
from scopesteps.projects.client import ProjectId

SuggestionKind = Literal["change_request", "answer_decision", "start_draft"]
SuggestionStatus = Literal["offered", "accepted", "dismissed"]


class SuggestionChangedError(ConflictError):
    code = "SUGGESTION_CHANGED"


class SuggestionDecidedError(ConflictError):
    """The suggestion was accepted or dismissed already; that never changes."""

    code = "SUGGESTION_ALREADY_DECIDED"


@dataclass(frozen=True)
class ProposedSuggestion:
    """A suggestion that passed the checks, before it is stored with its reply."""

    kind: SuggestionKind
    request_text: str | None = None
    """change_request: the text the change request would be submitted with."""
    version_id: UUID | None = None
    """answer_decision: the backlog version the decision is open in."""
    decision_id: UUID | None = None
    decision_subject: str | None = None
    answer: str | None = None


@dataclass(frozen=True)
class Suggestion:
    """A stored suggestion, one per reply message at most. Only its status ever changes."""

    message_id: MessageId
    project_id: ProjectId
    proposed: ProposedSuggestion
    created_at: datetime
    status: SuggestionStatus = "offered"
    revision: int = 1
    decided_by: UserId | None = None
    decided_at: datetime | None = None

    @property
    def kind(self) -> SuggestionKind:
        return self.proposed.kind

    def decided(
        self, status: Literal["accepted", "dismissed"], by: UserId, at: datetime
    ) -> Suggestion:
        """Record that a person accepted or dismissed it; deciding again the same way is a no-op.

        Raises SuggestionDecidedError when it was already decided the other way.
        """
        if self.status == status:
            return self
        if self.status != "offered":
            raise SuggestionDecidedError(
                f"This suggestion was already {self.status}.",
                details={"status": self.status, "current_revision": self.revision},
            )
        return replace(
            self, status=status, revision=self.revision + 1, decided_by=by, decided_at=at
        )
