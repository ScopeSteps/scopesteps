from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.agent.domain.ids import RunId
from scopesteps.agent.domain.model import ModelRequest, ModelResult
from scopesteps.agent.domain.run import Question, Run, RunStep
from scopesteps.backlog.client import CandidateProposal
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


class RunStore(Protocol):
    """Persistence for runs. Writes become durable only on `commit`."""

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
