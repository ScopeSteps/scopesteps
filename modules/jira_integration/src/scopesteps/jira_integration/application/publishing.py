"""Publishing approved versions through the outbox (ADR 0029).

Starting a publish only plans it and stores the plan as outbox entries. Each `advance` then sends
the next few entries, committing before and after every Jira call, so a retry, a second tab or
a crash never sends an operation twice: an entry left `sending` is checked against Jira first.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.identity.client import Actor, Permission, ProjectAccess
from scopesteps.jira_integration.application.connections import require_cipher
from scopesteps.jira_integration.application.ports import (
    ApprovedVersion,
    Checkpoint,
    ConnectionStore,
    GatewayFactory,
    JiraGateway,
    PublishStore,
    TokenCipher,
    VersionReader,
)
from scopesteps.jira_integration.domain.connection import JiraConnection
from scopesteps.jira_integration.domain.errors import (
    ITEM_FAILURES,
    JiraNotConnectedError,
    JiraRateLimitedError,
    JiraUnavailableError,
    PublishInProgressError,
    PublishNotRetryableError,
    VersionNotApprovedError,
)
from scopesteps.jira_integration.domain.ids import OutboxEntryId, PublishId
from scopesteps.jira_integration.domain.plan import IssueLink, Plan, issues_of, plan_publish
from scopesteps.jira_integration.domain.publish import (
    OutboxEntry,
    Publish,
    finish,
    outcome_summary,
)
from scopesteps.kernel.errors import DomainError, NotFoundError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

ENTRIES_PER_ADVANCE = 10
"""Each Jira call takes a few hundred milliseconds; ten keeps a request well under 30 seconds."""

RECENT_PUBLISHES = 20


@dataclass(frozen=True)
class PublishContext:
    """What every publishing use case reads and writes through."""

    connections: ConnectionStore
    publishes: PublishStore
    versions: VersionReader
    audit: AuditRecorder
    open_gateway: GatewayFactory
    cipher: TokenCipher | None
    summary: Callable[[str], str]
    """A title as a Jira summary: one line, cut to fit (`backlog`'s CSV rule, ADR 0014)."""
    project_link: Callable[[ProjectId], str]


def preview(context: PublishContext, access: ProjectAccess, version_id: UUID) -> Plan:
    """What publishing the version would do now. Calls nothing in Jira."""
    access.require(Permission.DECIDE_VERSIONS)
    _connection(context.connections, access.project_id)
    return _plan(context, _approved(context.versions, access, version_id))


def start(
    context: PublishContext,
    access: ProjectAccess,
    version_id: UUID,
    idempotency_key: str,
    now: datetime,
) -> Publish:
    """Stores the plan as an outbox. The same key returns the same publish; while another is
    still sending, asking for the same version returns it and another version is refused."""
    access.require(Permission.DECIDE_VERSIONS)
    replayed = context.publishes.publish_by_key(access.project_id, idempotency_key)
    if replayed is not None:
        return replayed
    _connection(context.connections, access.project_id)
    version = _approved(context.versions, access, version_id)
    unfinished = context.publishes.unfinished_publish(access.project_id)
    if unfinished is not None:
        if unfinished.version_id == version.id:
            return unfinished
        raise PublishInProgressError(
            "Another publish to Jira is still going. Let it finish first.",
            details={"publish_id": str(unfinished.id)},
        )
    plan = _plan(context, version)
    publish = Publish(
        id=PublishId(new_id()),
        project_id=access.project_id,
        version_id=version.id,
        idempotency_key=idempotency_key,
        status="sending",
        created_by=access.actor.user_id,
        created_by_name=access.actor.display_name,
        created_at=now,
    )
    entries = [
        OutboxEntry(
            id=OutboxEntryId(new_id()),
            publish_id=publish.id,
            position=position,
            item_id=operation.item_id,
            kind=operation.kind,
            operation=operation.operation,
            content=operation.content,
            jira_key=operation.jira_key,
        )
        for position, operation in enumerate(plan.operations)
    ]
    if not entries:
        publish = finish(publish, entries, now)
    context.publishes.add_publish(publish, entries)
    if publish.status != "sending":
        _record_outcome(context.audit, publish, entries, now)
    return publish


def view(context: PublishContext, access: ProjectAccess, publish: Publish) -> list[OutboxEntry]:
    access.require(Permission.DECIDE_VERSIONS)
    return context.publishes.entries(publish.id)


def recent(context: PublishContext, access: ProjectAccess) -> list[Publish]:
    access.require(Permission.DECIDE_VERSIONS)
    return context.publishes.recent_publishes(access.project_id, RECENT_PUBLISHES)


def issue_links(
    context: PublishContext, access: ProjectAccess
) -> tuple[JiraConnection | None, list[IssueLink]]:
    """Which Jira issue each item became, for anyone on the project to follow."""
    access.require_member()
    links = context.publishes.links(access.project_id)
    return context.connections.connection(access.project_id), list(links.values())


def advance(
    context: PublishContext,
    access: ProjectAccess,
    publish: Publish,
    checkpoint: Checkpoint,
    now: Callable[[], datetime],
) -> Publish:
    """Sends the next entries in order. A rate limit or an unreachable Jira stops early and
    leaves the rest for the next advance; an item Jira refuses is marked failed and the rest go
    on. When nothing is left, the publish is done, or failed if any item failed."""
    access.require(Permission.DECIDE_VERSIONS)
    if publish.status != "sending":
        return publish
    connection = context.connections.connection(publish.project_id)
    if connection is None:
        failed = replace(
            publish,
            status="failed",
            finished_at=now(),
            last_error=JiraNotConnectedError.code,
            revision=publish.revision + 1,
        )
        context.publishes.save_publish(failed)
        _record_outcome(context.audit, failed, context.publishes.entries(publish.id), now())
        return failed
    cipher = require_cipher(context.cipher)
    gateway = context.open_gateway(
        connection.site_url, connection.email, cipher.decrypt(connection.token_ciphertext)
    )
    entries = context.publishes.entries(publish.id)
    waiting = [entry for entry in entries if entry.state in ("pending", "sending")]
    stopped: str | None = None
    for entry in waiting[:ENTRIES_PER_ADVANCE]:
        try:
            _send(context, connection, gateway, entry, checkpoint)
        except (JiraRateLimitedError, JiraUnavailableError) as error:
            stopped = error.code
            break
        except DomainError as error:
            if error.code not in ITEM_FAILURES:
                # Jira refused the account or the project: nothing else would get through.
                for left in context.publishes.entries(publish.id):
                    if left.state in ("pending", "sending"):
                        context.publishes.save_entry(left.failed(error.code))
                stopped = error.code
                break
            context.publishes.save_entry(entry.failed(error.code))
        checkpoint()
    entries = context.publishes.entries(publish.id)
    finished = finish(replace(publish, last_error=stopped), entries, now())
    if finished.status != "sending":
        finished = replace(finished, last_error=stopped)
        _record_outcome(context.audit, finished, entries, now())
    elif stopped != publish.last_error:
        finished = replace(finished, revision=publish.revision + 1)
    if finished != publish:
        context.publishes.save_publish(finished)
    return finished


def retry(context: PublishContext, access: ProjectAccess, publish: Publish) -> Publish:
    """Sends the failed entries again; what was created stays and is never created twice."""
    access.require(Permission.DECIDE_VERSIONS)
    if publish.status != "failed":
        raise PublishNotRetryableError("Only a publish that failed can be tried again.")
    unfinished = context.publishes.unfinished_publish(publish.project_id)
    if unfinished is not None:
        raise PublishInProgressError(
            "Another publish to Jira is still going. Let it finish first.",
            details={"publish_id": str(unfinished.id)},
        )
    _connection(context.connections, publish.project_id)
    for entry in context.publishes.entries(publish.id):
        if entry.state == "failed":
            context.publishes.save_entry(replace(entry, state="pending", error_code=None))
    retried = replace(
        publish, status="sending", finished_at=None, last_error=None, revision=publish.revision + 1
    )
    context.publishes.save_publish(retried)
    return retried


@dataclass(frozen=True)
class AfterApproval:
    publish_id: PublishId | None
    problem: str | None
    """Why no publish started though one was asked for, as an error code."""


def publish_after_approval(
    context: PublishContext,
    access: ProjectAccess,
    version_id: UUID,
    requested: bool,
    now: datetime,
) -> AfterApproval:
    """Starts publishing a version just approved, when the approver ticked "Also publish to
    Jira" or the project publishes automatically. Never undoes the approval: a refusal comes
    back as `problem`. Keyed by the version, so approving again cannot start a second publish."""
    connection = context.connections.connection(access.project_id)
    wanted = requested or (connection is not None and connection.auto_publish)
    if not wanted:
        return AfterApproval(None, None)
    try:
        publish = start(context, access, version_id, f"after-approval:{version_id}", now)
    except DomainError as error:
        return AfterApproval(None, error.code)
    return AfterApproval(publish.id, None)


def publish_for(context: PublishContext, publish_id: PublishId) -> Publish:
    """A publish by id, before access to its project is resolved."""
    publish = context.publishes.publish(publish_id)
    if publish is None:
        raise NotFoundError("Publish not found")
    return publish


def _send(
    context: PublishContext,
    connection: JiraConnection,
    gateway: JiraGateway,
    entry: OutboxEntry,
    checkpoint: Checkpoint,
) -> None:
    project = connection.jira_project
    links = context.publishes.links(connection.project_id)
    unconfirmed = entry.state == "sending"
    sending = entry.sending()
    context.publishes.save_entry(sending)
    checkpoint()
    if entry.operation == "close":
        key = entry.jira_key or links[entry.item_id].jira_key
        gateway.close_issue(key)
        link = links[entry.item_id]
        context.publishes.save_link(connection.project_id, replace(link, closed=True))
        context.publishes.save_entry(sending.done(key))
        return
    content = entry.content
    if content is None:  # Only a close has no content; the plan never stores one otherwise.
        raise ValueError(f"outbox entry {entry.id} has no content")
    parent_key: str | None = None
    if content.parent_item_id is not None:
        parent = links.get(content.parent_item_id)
        if parent is None:
            raise _ParentNotPublishedError("Its parent was not published, so it was skipped.")
        parent_key = parent.jira_key
    if entry.operation == "update" and entry.jira_key is not None:
        gateway.update_issue(entry.jira_key, project, content, parent_key)
        link = links[entry.item_id]
        context.publishes.save_link(
            connection.project_id,
            replace(link, fingerprint=content.fingerprint(), closed=False),
        )
        context.publishes.save_entry(sending.done(entry.jira_key))
        return
    found = gateway.find_issue(project, content.marker) if unconfirmed else None
    issue = found or gateway.create_issue(project, content, parent_key)
    context.publishes.save_link(
        connection.project_id,
        IssueLink(content.item_id, content.kind, issue.key, issue.id, content.fingerprint()),
    )
    context.publishes.save_entry(sending.done(issue.key))


class _ParentNotPublishedError(DomainError):
    code = "PARENT_NOT_PUBLISHED"


def _connection(store: ConnectionStore, project_id: ProjectId) -> JiraConnection:
    connection = store.connection(project_id)
    if connection is None:
        raise JiraNotConnectedError("Connect this project to Jira first, in Project settings.")
    return connection


def _approved(reader: VersionReader, access: ProjectAccess, version_id: UUID) -> ApprovedVersion:
    version = reader.version(version_id)
    if version is None or version.project_id != access.project_id:
        raise NotFoundError("Backlog version not found")
    if not version.approved:
        raise VersionNotApprovedError(
            "Only an approved version can be published to Jira. Approve it first."
        )
    return version


def _plan(context: PublishContext, version: ApprovedVersion) -> Plan:
    issues = issues_of(version.items, context.summary, context.project_link(version.project_id))
    return plan_publish(issues, context.publishes.links(version.project_id))


def _record_outcome(
    audit: AuditRecorder, publish: Publish, entries: list[OutboxEntry], now: datetime
) -> None:
    done = publish.status == "done"
    audit.record(
        project_id=publish.project_id,
        actor=AuditActor.user(Actor(publish.created_by, publish.created_by_name)),
        type=EventType.JIRA_PUBLISHED if done else EventType.JIRA_PUBLISH_FAILED,
        subjects=[Subject(SubjectKind.BACKLOG_VERSION, publish.version_id)],
        summary=("Published to Jira: " if done else "Publishing to Jira stopped: ")
        + outcome_summary(entries),
        occurred_at=now,
    )
