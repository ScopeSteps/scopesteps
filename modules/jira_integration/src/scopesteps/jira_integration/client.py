"""What other modules and the composition root use from `jira_integration` (ADR 0029)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import httpx
from sqlalchemy.orm import Session, sessionmaker

from scopesteps.audit.client import audit_recorder
from scopesteps.backlog.client import jira_summary
from scopesteps.identity.client import ProjectAccess
from scopesteps.infrastructure.database import utc_now
from scopesteps.jira_integration.application import connections, publishing
from scopesteps.jira_integration.application.ports import GatewayFactory, JiraGateway, TokenCipher
from scopesteps.jira_integration.application.publishing import AfterApproval, PublishContext
from scopesteps.jira_integration.domain.ids import PublishId
from scopesteps.jira_integration.infrastructure.crypto import FernetTokenCipher, valid_key
from scopesteps.jira_integration.infrastructure.jira_http import HttpJiraGateway
from scopesteps.jira_integration.infrastructure.repository import SqlJiraStore
from scopesteps.jira_integration.infrastructure.versions import BacklogVersions
from scopesteps.projects.client import ProjectId


@dataclass(frozen=True)
class JiraRuntime:
    """How this server reaches Jira, set once at start-up."""

    cipher: TokenCipher | None
    """None when `JIRA_TOKEN_KEY` is not set: connecting is then refused."""
    open_gateway: GatewayFactory
    app_base_url: str


def jira_runtime(
    token_key: str | None, app_base_url: str, transport: httpx.BaseTransport | None = None
) -> JiraRuntime:
    """The runtime for a key from settings. `transport` replaces the network, for tests."""

    def open_gateway(site_url: str, email: str, api_token: str) -> JiraGateway:
        return HttpJiraGateway(site_url, email, api_token, transport)

    return JiraRuntime(
        cipher=FernetTokenCipher(token_key) if token_key else None,
        open_gateway=open_gateway,
        app_base_url=app_base_url.rstrip("/"),
    )


def publish_context(session: Session, runtime: JiraRuntime) -> PublishContext:
    store = SqlJiraStore(session)

    def project_link(project_id: ProjectId) -> str:
        return f"{runtime.app_base_url}/projects/{project_id}/backlog"

    return PublishContext(
        connections=store,
        publishes=store,
        versions=BacklogVersions(session),
        audit=audit_recorder(session),
        open_gateway=runtime.open_gateway,
        cipher=runtime.cipher,
        summary=jira_summary,
        project_link=project_link,
    )


def publish_after_approval(
    session: Session,
    runtime: JiraRuntime,
    access: ProjectAccess,
    version_id: UUID,
    requested: bool,
    now: datetime,
) -> AfterApproval:
    """Call after the approval has committed; commits the publish it starts, if any. Nothing is
    sent to Jira here: the publish's advances send it."""
    started = publishing.publish_after_approval(
        publish_context(session, runtime), access, version_id, requested, now
    )
    session.commit()
    return started


PUBLISHES_PER_ROUND = 5
"""Each holds at most ten Jira calls, so one round stays well under the job's lease."""


def send_due_publishes(
    session_factory: sessionmaker[Session],
    runtime: JiraRuntime,
    now: Callable[[], datetime] = utc_now,
) -> int:
    """One round of the background sender (ADR 0029): checks any saved token not checked in a
    day, then sends the next entries of up to five due publishes, each claimed under a lease and
    committed as it goes. Returns how many publishes it moved. Safe to run in several processes
    at once."""
    with session_factory() as session:
        connections.check_saved_tokens(
            SqlJiraStore(session), runtime.open_gateway, runtime.cipher, now()
        )
        session.commit()
    moved = 0
    for _ in range(PUBLISHES_PER_ROUND):
        with session_factory() as session:
            sent = publishing.send_due(publish_context(session, runtime), session.commit, now)
            session.commit()
        if sent is None:
            break
        moved += 1
    return moved


AfterApprovalHook = Callable[[Session, ProjectAccess, UUID, bool, datetime], AfterApproval]

__all__ = [
    "AfterApproval",
    "AfterApprovalHook",
    "JiraRuntime",
    "PublishId",
    "jira_runtime",
    "publish_after_approval",
    "publish_context",
    "send_due_publishes",
    "valid_key",
]
