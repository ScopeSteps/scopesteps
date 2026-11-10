"""Connecting a project to Jira Cloud. Only an approver does this (ADR 0029)."""

from dataclasses import dataclass, replace
from datetime import datetime

from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.identity.client import Permission, ProjectAccess
from scopesteps.jira_integration.application.ports import (
    ConnectionStore,
    GatewayFactory,
    TokenCipher,
)
from scopesteps.jira_integration.domain.connection import (
    JiraConnection,
    normalise_project_key,
    normalise_site_url,
)
from scopesteps.jira_integration.domain.errors import (
    ConnectionChangedError,
    JiraNotConfiguredError,
    JiraNotConnectedError,
)
from scopesteps.kernel.errors import InvalidInputError

MAX_EMAIL_CHARS = 254


@dataclass(frozen=True)
class Connect:
    site_url: str
    email: str
    api_token: str
    project_key: str


def require_cipher(cipher: TokenCipher | None) -> TokenCipher:
    if cipher is None:
        raise JiraNotConfiguredError(
            "Jira publishing is not set up on this server: it needs JIRA_TOKEN_KEY."
        )
    return cipher


def view_connection(store: ConnectionStore, access: ProjectAccess) -> JiraConnection | None:
    access.require(Permission.DECIDE_VERSIONS)
    return store.connection(access.project_id)


def connect(
    store: ConnectionStore,
    audit: AuditRecorder,
    open_gateway: GatewayFactory,
    cipher: TokenCipher | None,
    access: ProjectAccess,
    command: Connect,
    now: datetime,
) -> JiraConnection:
    """Tests the details against Jira, then saves them, replacing any earlier connection. Moving
    to another site or Jira project forgets the issues earlier publishes made, so nothing is
    updated in the wrong place; the auto-publish choice is kept."""
    access.require(Permission.DECIDE_VERSIONS)
    guard = require_cipher(cipher)
    site_url = normalise_site_url(command.site_url)
    email = command.email.strip()
    token = command.api_token.strip()
    if not email or len(email) > MAX_EMAIL_CHARS or "@" not in email:
        raise InvalidInputError("Enter the email address of the Jira account.")
    if not token:
        raise InvalidInputError("Enter an API token for the Jira account.")
    jira_project = open_gateway(site_url, email, token).project(
        normalise_project_key(command.project_key)
    )
    earlier = store.connection(access.project_id)
    moved = earlier is not None and (
        earlier.site_url != site_url or earlier.jira_project.id != jira_project.id
    )
    if moved:
        store.forget_links(access.project_id)
    connection = JiraConnection(
        project_id=access.project_id,
        site_url=site_url,
        email=email,
        token_ciphertext=guard.encrypt(token),
        jira_project=jira_project,
        auto_publish=earlier.auto_publish if earlier else False,
        revision=earlier.revision + 1 if earlier else 1,
        connected_by=access.actor.user_id,
        connected_at=now,
        checked_at=now,
    )
    store.save_connection(connection)
    audit.record(
        project_id=access.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.JIRA_CONNECTED,
        subjects=[Subject(SubjectKind.PROJECT, access.project_id)],
        summary=f"Connected Jira project {jira_project.key}",
        occurred_at=now,
    )
    return connection


def test_connection(
    store: ConnectionStore,
    open_gateway: GatewayFactory,
    cipher: TokenCipher | None,
    access: ProjectAccess,
    now: datetime,
) -> JiraConnection:
    """Checks the saved details still work, and refreshes the issue types items map to."""
    access.require(Permission.DECIDE_VERSIONS)
    guard = require_cipher(cipher)
    connection = _require(store, access)
    jira_project = open_gateway(
        connection.site_url, connection.email, guard.decrypt(connection.token_ciphertext)
    ).project(connection.jira_project.key)
    checked = replace(connection, jira_project=jira_project, checked_at=now)
    store.save_connection(checked)
    return checked


def disconnect(
    store: ConnectionStore, audit: AuditRecorder, access: ProjectAccess, now: datetime
) -> None:
    """Deletes the connection and its token. What was published stays in Jira and stays linked,
    so connecting the same Jira project again updates those issues."""
    access.require(Permission.DECIDE_VERSIONS)
    connection = store.connection(access.project_id)
    if connection is None:
        return
    store.delete_connection(access.project_id)
    audit.record(
        project_id=access.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.JIRA_DISCONNECTED,
        subjects=[Subject(SubjectKind.PROJECT, access.project_id)],
        summary=f"Disconnected Jira project {connection.jira_project.key}",
        occurred_at=now,
    )


def set_auto_publish(
    store: ConnectionStore,
    audit: AuditRecorder,
    access: ProjectAccess,
    auto_publish: bool,
    expected_revision: int,
    now: datetime,
) -> JiraConnection:
    access.require(Permission.DECIDE_VERSIONS)
    connection = _require(store, access)
    if connection.revision != expected_revision:
        raise ConnectionChangedError(
            "Someone changed the Jira settings since you opened them. Reload and try again."
        )
    if connection.auto_publish == auto_publish:
        return connection
    changed = replace(connection, auto_publish=auto_publish, revision=connection.revision + 1)
    store.save_connection(changed)
    audit.record(
        project_id=access.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.JIRA_SETTINGS_CHANGED,
        subjects=[Subject(SubjectKind.PROJECT, access.project_id)],
        summary="Turned automatic Jira publishing " + ("on" if auto_publish else "off"),
        occurred_at=now,
    )
    return changed


def _require(store: ConnectionStore, access: ProjectAccess) -> JiraConnection:
    connection = store.connection(access.project_id)
    if connection is None:
        raise JiraNotConnectedError("This project is not connected to Jira.")
    return connection
