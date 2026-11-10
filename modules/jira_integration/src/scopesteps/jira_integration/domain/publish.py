from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal
from uuid import UUID

from scopesteps.identity.client import UserId
from scopesteps.jira_integration.domain.ids import OutboxEntryId, PublishId
from scopesteps.jira_integration.domain.plan import IssueContent, IssueKind, Operation
from scopesteps.projects.client import ProjectId

PublishStatus = Literal["sending", "done", "failed"]
EntryState = Literal["pending", "sending", "done", "failed"]


@dataclass(frozen=True)
class OutboxEntry:
    """One operation of a publish. `sending` is written and committed before Jira is called, so
    an entry found still sending after a crash or timeout is one whose outcome is unknown."""

    id: OutboxEntryId
    publish_id: PublishId
    position: int
    item_id: UUID
    kind: IssueKind
    operation: Operation
    content: IssueContent | None
    jira_key: str | None
    state: EntryState = "pending"
    error_code: str | None = None
    attempts: int = 0

    def sending(self) -> OutboxEntry:
        return replace(self, state="sending", attempts=self.attempts + 1)

    def done(self, jira_key: str) -> OutboxEntry:
        return replace(self, state="done", jira_key=jira_key, error_code=None)

    def failed(self, code: str) -> OutboxEntry:
        return replace(self, state="failed", error_code=code)


@dataclass(frozen=True)
class Publish:
    """Sending one approved version to Jira. Its entries are the outbox (ADR 0029)."""

    id: PublishId
    project_id: ProjectId
    version_id: UUID
    """The approved backlog version sent."""
    idempotency_key: str
    status: PublishStatus
    created_by: UserId
    created_by_name: str
    created_at: datetime
    finished_at: datetime | None = None
    last_error: str | None = None
    """Why the last attempt stopped early (a rate limit, Jira unreachable), until the next."""
    revision: int = 1


def finish(publish: Publish, entries: list[OutboxEntry], now: datetime) -> Publish:
    """Done when every entry is; failed when one failed and none is left to send."""
    if any(entry.state in ("pending", "sending") for entry in entries):
        return publish
    failed = any(entry.state == "failed" for entry in entries)
    return replace(
        publish,
        status="failed" if failed else "done",
        finished_at=now,
        last_error=None,
        revision=publish.revision + 1,
    )


def outcome_summary(entries: list[OutboxEntry]) -> str:
    """For the activity log: counts only, never titles."""
    done = [entry for entry in entries if entry.state == "done"]
    parts = [
        f"{sum(1 for entry in done if entry.operation == operation)} {label}"
        for operation, label in (("create", "created"), ("update", "updated"), ("close", "closed"))
    ]
    failed = sum(1 for entry in entries if entry.state == "failed")
    if failed:
        parts.append(f"{failed} failed")
    return ", ".join(parts)
