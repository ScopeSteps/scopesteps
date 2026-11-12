"""Connecting a project to Jira Cloud. Only an approver does this (ADR 0029)."""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.identity.client import Permission, ProjectAccess
from scopesteps.jira_integration.application.ports import (
    ConnectionStore,
    GatewayFactory,
    JiraNotices,
    TokenCipher,
)
from scopesteps.jira_integration.domain.connection import (
    JiraConnection,
    Publishers,
    check_token_expiry,
    normalise_project_key,
    normalise_site_url,
)
from scopesteps.jira_integration.domain.errors import (
    ConnectionChangedError,
    JiraAuthFailedError,
    JiraNotConfiguredError,
    JiraNotConnectedError,
)
from scopesteps.kernel.errors import DomainError, InvalidInputError

MAX_EMAIL_CHARS = 254


@dataclass(frozen=True)
class Connect:
    site_url: str
    email: str
    api_token: str
    project_key: str
    token_expires_on: date | None = None


def require_cipher(cipher: TokenCipher | None) -> TokenCipher:
    if cipher is None:
        raise JiraNotConfiguredError(
            "Jira publishing is not set up on this server: it needs JIRA_TOKEN_KEY."
        )
    return cipher


def view_connection(store: ConnectionStore, access: ProjectAccess) -> JiraConnection | None:
    """Any member sees whether the project is connected, so the app knows what to offer."""
    access.require_member()
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
    expires_on = check_token_expiry(command.token_expires_on, now.date())
    gateway = open_gateway(site_url, email, token)
    account = gateway.account()
    jira_project = gateway.project(normalise_project_key(command.project_key))
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
        publishers=earlier.publishers if earlier else "approvers",
        account=account,
        token_expires_on=expires_on,
    )
    store.save_connection(connection)
    audit.record(
        project_id=access.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.JIRA_CONNECTED,
        subjects=[Subject(SubjectKind.PROJECT, access.project_id)],
        summary=f"Connected Jira project {jira_project.key} as {account.name}",
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
    gateway = open_gateway(
        connection.site_url, connection.email, guard.decrypt(connection.token_ciphertext)
    )
    try:
        account = gateway.account()
    except JiraAuthFailedError:
        store.save_connection(connection.rejected(now))
        raise
    jira_project = gateway.project(connection.jira_project.key)
    checked = replace(
        connection,
        account=account,
        jira_project=jira_project,
        checked_at=now,
        token_rejected_at=None,
    )
    store.save_connection(checked)
    return checked


TOKEN_CHECK_EVERY = timedelta(days=1)


def check_saved_tokens(
    store: ConnectionStore,
    open_gateway: GatewayFactory,
    cipher: TokenCipher | None,
    notices: JiraNotices,
    now: datetime,
) -> int:
    """The background sender's daily look at each saved token: one read-only call per project,
    so a revoked token shows before anyone tries to publish. Jira unreachable changes nothing.
    The approvers hear once when the token expires within 14 days, and once when it stops
    working. Returns how many tokens were found refused."""
    if cipher is None:
        return 0
    refused = 0
    for connection in store.connections_checked_before(now - TOKEN_CHECK_EVERY):
        gateway = open_gateway(
            connection.site_url, connection.email, cipher.decrypt(connection.token_ciphertext)
        )
        try:
            account = gateway.account()
        except JiraAuthFailedError:
            checked = replace(connection.rejected(now), checked_at=now)
            refused += 1
        except DomainError:
            checked = connection
        else:
            checked = replace(connection, account=account, checked_at=now)
        if checked is not connection:
            store.save_connection(checked)
        notice = checked.token_notice(now.date())
        if notice is not None:
            notices.token_needs_attention(checked, notice, now)
    return refused


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


def change_settings(
    store: ConnectionStore,
    audit: AuditRecorder,
    access: ProjectAccess,
    expected_revision: int,
    now: datetime,
    *,
    auto_publish: bool | None = None,
    publishers: Publishers | None = None,
    token_expires_on: date | None = None,
) -> JiraConnection:
    """Automatic publishing, and who may publish. Fields left as None are unchanged."""
    access.require(Permission.DECIDE_VERSIONS)
    connection = _require(store, access)
    if connection.revision != expected_revision:
        raise ConnectionChangedError(
            "Someone changed the Jira settings since you opened them. Reload and try again."
        )
    changed = replace(
        connection,
        auto_publish=connection.auto_publish if auto_publish is None else auto_publish,
        publishers=connection.publishers if publishers is None else publishers,
        token_expires_on=connection.token_expires_on
        if token_expires_on is None
        else check_token_expiry(token_expires_on, now.date()),
    )
    if changed == connection:
        return connection
    changed = replace(changed, revision=connection.revision + 1)
    store.save_connection(changed)
    parts: list[str] = []
    if changed.auto_publish != connection.auto_publish:
        parts.append(
            "turned automatic Jira publishing " + ("on" if changed.auto_publish else "off")
        )
    if changed.token_expires_on != connection.token_expires_on:
        parts.append(f"noted that the Jira token expires on {changed.token_expires_on}")
    if changed.publishers != connection.publishers:
        parts.append(
            "let Editors publish to Jira"
            if changed.publishers == "approvers_and_editors"
            else "let only Approvers publish to Jira"
        )
    audit.record(
        project_id=access.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.JIRA_SETTINGS_CHANGED,
        subjects=[Subject(SubjectKind.PROJECT, access.project_id)],
        summary=_sentence(" and ".join(parts)),
        occurred_at=now,
    )
    return changed


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def _require(store: ConnectionStore, access: ProjectAccess) -> JiraConnection:
    connection = store.connection(access.project_id)
    if connection is None:
        raise JiraNotConnectedError("This project is not connected to Jira.")
    return connection
