"""What the use cases need from Jira, the database, the backlog and the key that guards tokens."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.jira_integration.domain.connection import (
    JiraAccount,
    JiraConnection,
    JiraProject,
    TokenNotice,
)
from scopesteps.jira_integration.domain.ids import PublishId
from scopesteps.jira_integration.domain.plan import ApprovedItem, IssueContent, IssueLink
from scopesteps.jira_integration.domain.publish import OutboxEntry, Publish
from scopesteps.projects.client import ProjectId


@dataclass(frozen=True)
class JiraIssue:
    id: str
    key: str


class JiraGateway(Protocol):
    """Jira Cloud's REST API for one site and account. Every method raises a JiraError subclass
    (`domain.errors`) for a refusal, never the HTTP library's own errors."""

    def account(self) -> JiraAccount:
        """The account the token belongs to; raises JiraAuthFailedError when Jira refuses it."""
        ...

    def project(self, key: str) -> JiraProject:
        """Finds the project and the issue types items map to."""
        ...

    def create_issue(
        self, project: JiraProject, issue: IssueContent, parent_key: str | None
    ) -> JiraIssue: ...

    def update_issue(
        self, key: str, project: JiraProject, issue: IssueContent, parent_key: str | None
    ) -> None: ...

    def close_issue(self, key: str) -> None:
        """Moves the issue to a done status; one already done is left as it is."""
        ...

    def find_issue(self, project: JiraProject, marker: str) -> JiraIssue | None:
        """The project's issue whose description holds `marker`, if there is one."""
        ...


GatewayFactory = Callable[[str, str, str], JiraGateway]
"""Opens a gateway for a site URL, an account email and its API token."""


class TokenCipher(Protocol):
    def encrypt(self, token: str) -> bytes: ...

    def decrypt(self, ciphertext: bytes) -> str: ...


class ConnectionStore(Protocol):
    def connection(self, project_id: ProjectId) -> JiraConnection | None: ...

    def save_connection(self, connection: JiraConnection) -> None: ...

    def delete_connection(self, project_id: ProjectId) -> None: ...

    def connections_checked_before(self, moment: datetime) -> list[JiraConnection]:
        """Connections whose token was last checked before `moment` and not refused since."""
        ...

    def forget_links(self, project_id: ProjectId) -> None:
        """Drops what earlier publishes created, when the project moves to another Jira project."""
        ...


class PublishStore(Protocol):
    def publish(self, publish_id: PublishId) -> Publish | None: ...

    def publish_by_key(self, project_id: ProjectId, idempotency_key: str) -> Publish | None: ...

    def unfinished_publish(self, project_id: ProjectId) -> Publish | None: ...

    def recent_publishes(self, project_id: ProjectId, limit: int) -> list[Publish]: ...

    def add_publish(self, publish: Publish, entries: list[OutboxEntry]) -> None: ...

    def save_publish(self, publish: Publish) -> None: ...

    def claim_publish(
        self, publish_id: PublishId, now: datetime, until: datetime
    ) -> Publish | None:
        """Leases a sending publish nobody holds, in one conditional update; None if it is held,
        finished or missing."""
        ...

    def claim_due_publish(self, now: datetime, until: datetime) -> Publish | None:
        """Leases the oldest sending publish that nobody holds and that is not waiting."""
        ...

    def entries(self, publish_id: PublishId) -> list[OutboxEntry]:
        """In the order they are sent."""
        ...

    def save_entry(self, entry: OutboxEntry) -> None: ...

    def links(self, project_id: ProjectId) -> dict[UUID, IssueLink]: ...

    def save_link(self, project_id: ProjectId, link: IssueLink) -> None: ...


@dataclass(frozen=True)
class ApprovedVersion:
    id: UUID
    project_id: ProjectId
    approved: bool
    items: tuple[ApprovedItem, ...]


class VersionReader(Protocol):
    def version(self, version_id: UUID) -> ApprovedVersion | None: ...


Checkpoint = Callable[[], None]
"""Commits what the use case has written so far, before it calls Jira (ADR 0029)."""


class JiraNotices(Protocol):
    """Tells people how Jira publishing went, in the caller's transaction (ADR 0029 note of
    2026-11-11). Counts and ids only: never titles, Jira's answers or the token."""

    def publish_finished(self, publish: Publish, counts: Mapping[str, int], now: datetime) -> None:
        """The person who started the publish, or the approver of an automatic one."""
        ...

    def token_needs_attention(
        self, connection: JiraConnection, notice: TokenNotice, now: datetime
    ) -> None:
        """The project's approvers, once per notice key."""
        ...
