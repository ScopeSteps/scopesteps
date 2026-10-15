from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.agent.domain.conversation import Message
from scopesteps.agent.domain.ids import MessageId, RunId
from scopesteps.agent.domain.model import ModelRequest, ModelResult
from scopesteps.agent.domain.run import Question, Run, RunStep
from scopesteps.backlog.client import (
    BacklogOutline,
    BacklogVersion,
    CandidateProposal,
    ChangeProposal,
    SavedChange,
)
from scopesteps.change_control.client import (
    ChangeAnalysis,
    ChangeRequestRef,
    ChangeSummary,
    OpenChangeRequest,
)
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceBlockId, SourceVersionId


class ModelProvider(Protocol):
    """The only way agent code reaches a model.

    One configured provider per process. Implementations never retry, fall back to another model
    or provider, or switch billing tiers; they raise ModelProviderError and the caller decides.
    """

    def generate(self, request: ModelRequest) -> ModelResult: ...


@dataclass(frozen=True)
class Receipt:
    """An accepted request, kept so a retry with the same Idempotency-Key does not act twice."""

    actor_id: UserId
    idempotency_key: str
    operation: str
    run_id: RunId
    fingerprint: str
    created_at: datetime


@dataclass(frozen=True)
class Passage:
    """A pinned source paragraph, as the agent reads it."""

    block_id: SourceBlockId
    source_version_id: SourceVersionId
    source_kind: str
    ordinal: int
    text: str


class PassageReader(Protocol):
    def load(self, project_id: ProjectId, version_ids: Sequence[UUID]) -> list[Passage]:
        """Paragraphs in order. Raises NotFoundError if a version is not in the project."""
        ...

    def removed(self, project_id: ProjectId, version_ids: Sequence[UUID]) -> set[UUID]:
        """Those of the versions whose source the project has removed."""
        ...


class CandidateStore(Protocol):
    """Where a finished draft becomes a draft backlog version. The backlog module owns it."""

    def problems(self, proposal: CandidateProposal) -> list[str]:
        """Why the proposal would be refused; empty when `save` will accept it. Read-only."""
        ...

    def save(self, proposal: CandidateProposal, now: datetime) -> None:
        """Save within the run's transaction. A run that already has a candidate keeps it."""
        ...


class DraftAnswers(Protocol):
    """Where a changed clarification answer reaches the draft that uses it. The backlog module
    owns it."""

    def change_answer(
        self, run_id: RunId, question_id: UUID, answer: str, decided_by: UserId, now: datetime
    ) -> UUID | None:
        """Write the answer into the draft made from the run, moving it to its next revision, in
        the caller's transaction. None when the run made no draft. Raises VersionNotDraftError
        once that draft is approved or rejected."""
        ...


class ChangeStore(Protocol):
    """Where a change run's proposal becomes a candidate in review. The backlog module owns it."""

    def problems(self, proposal: ChangeProposal) -> list[str]:
        """Why the proposal would be refused; empty when `save` will accept it. Read-only."""
        ...

    def save(self, proposal: ChangeProposal, now: datetime) -> SavedChange:
        """Save within the run's transaction, building on the baseline, which is only read."""
        ...


class ChangeRequests(Protocol):
    """Change requests and their text, owned by change control and sources. Every write joins
    the caller's transaction (ADR 0011)."""

    def record_text(
        self, project_id: ProjectId, text: str, recorded_by: UserId, now: datetime
    ) -> SourceVersionId:
        """Store the request's text as an immutable source version a change can cite."""
        ...

    def open(self, command: OpenChangeRequest, now: datetime) -> ChangeRequestRef: ...

    def analyzed(
        self, run_id: RunId, analysis: ChangeAnalysis, now: datetime
    ) -> ChangeSummary | None:
        """Record the analysis; returns the candidate's counts, None when no change is needed."""
        ...

    def failed(self, run_id: RunId, code: str, now: datetime) -> None: ...


@dataclass(frozen=True)
class Baseline:
    version: BacklogVersion
    number: int
    """1 for v1."""


class ProjectContext(Protocol):
    """What the agent reads about a project from the modules that own it."""

    def current_source_versions(self, project_id: ProjectId) -> list[SourceVersionId]:
        """The newest version of each source the project has not removed."""
        ...

    def backlog(self, project_id: ProjectId) -> BacklogOutline | None:
        """The newest version in flight, or else the baseline."""
        ...

    def has_baseline(self, project_id: ProjectId) -> bool: ...

    def baseline(self, project_id: ProjectId) -> Baseline | None:
        """The project's newest approved version, whole, with its number."""
        ...

    def version(self, version_id: UUID) -> BacklogVersion | None:
        """Any backlog version, whole. Performs no access check."""
        ...


@dataclass(frozen=True)
class MessageCursor:
    """The position after the last message of a page, in conversation order."""

    created_at: datetime
    id: MessageId


class ConversationStore(Protocol):
    """Persistence for a project's conversation. Messages are only ever added."""

    def add_messages(self, messages: Sequence[Message]) -> None: ...

    def newest_messages(
        self, project_id: ProjectId, *, before: MessageCursor | None, limit: int
    ) -> list[Message]:
        """Up to `limit` messages ordered by time then id, both descending, before `before`."""
        ...

    def run_messages(self, run_id: RunId) -> list[Message]:
        """The messages that belong to the run, oldest first."""
        ...

    def claim_turn(self, project_id: ProjectId) -> bool:
        """Take the project's turn to start agent work from the conversation, in the caller's
        transaction. False when a concurrent request took it first."""
        ...

    def active_run(self, project_id: ProjectId) -> Run | None:
        """The newest run that is created, running or waiting for answers."""
        ...

    def answered_questions(self, project_id: ProjectId) -> list[Question]:
        """Every answered question of the project's runs, in the order they were answered."""
        ...

    def questions_by_id(self, ids: Sequence[UUID]) -> list[Question]: ...


class RunStore(ConversationStore, Protocol):
    """Persistence for runs and the conversation. Writes become durable only on `commit`."""

    def get_run(self, run_id: RunId) -> Run | None: ...

    def add_run(self, run: Run) -> None: ...

    def save_run(self, run: Run, *, expected_revision: int) -> bool:
        """Compare-and-set: False, and nothing written, if the stored revision has moved on."""
        ...

    def add_usage(self, run: Run, *, since: Run) -> None:
        """Add the usage between two snapshots without touching state, for discarded steps."""
        ...

    def add_steps(self, steps: Sequence[RunStep]) -> None:
        """Append steps, numbered after the run's existing ones in the same transaction."""
        ...

    def steps(self, run_id: RunId) -> list[RunStep]: ...

    def questions(self, run_id: RunId) -> list[Question]: ...

    def save_questions(self, questions: Sequence[Question]) -> None:
        """Insert new questions or update existing ones by id."""
        ...

    def project_cost_microusd(self, project_id: ProjectId) -> int: ...

    def find_receipt(self, actor_id: UserId, idempotency_key: str) -> Receipt | None: ...

    def add_receipt(self, receipt: Receipt) -> None: ...

    def commit(self) -> None: ...
