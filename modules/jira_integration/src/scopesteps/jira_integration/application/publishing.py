"""Publishing approved versions through the outbox (ADR 0029).

Starting a publish only plans it and stores the plan as outbox entries. Each `advance` then sends
the next few entries, committing before and after every Jira call, so a retry, a second tab or
a crash never sends an operation twice: an entry left `sending` is checked against Jira first.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
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
    JiraNotices,
    PublishStore,
    TokenCipher,
    VersionReader,
)
from scopesteps.jira_integration.domain.connection import JiraConnection
from scopesteps.jira_integration.domain.errors import (
    ITEM_FAILURES,
    JiraAuthFailedError,
    JiraNotConnectedError,
    JiraRateLimitedError,
    JiraTokenExpiredError,
    JiraTokenRejectedError,
    JiraUnavailableError,
    PublishInProgressError,
    PublishNotRetryableError,
    VersionNotApprovedError,
)
from scopesteps.jira_integration.domain.ids import OutboxEntryId, PublishId
from scopesteps.jira_integration.domain.plan import IssueLink, Plan, issues_of, plan_publish
from scopesteps.jira_integration.domain.publish import (
    MAX_ENTRY_ATTEMPTS,
    OutboxEntry,
    Publish,
    backoff,
    finish,
    outcome_counts,
    outcome_summary,
)
from scopesteps.kernel.errors import DomainError, NotFoundError, PermissionDeniedError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

ENTRIES_PER_ADVANCE = 10
"""Each Jira call takes a few hundred milliseconds; ten keeps a request well under 30 seconds."""

RECENT_PUBLISHES = 20

LEASE = timedelta(minutes=5)
"""Longer than a batch can take (ten calls of at most 20 seconds each), so a lease only runs out
when its sender died; another sender then takes the publish over."""

logger = logging.getLogger(__name__)


def can_publish(access: ProjectAccess, connection: JiraConnection | None) -> bool:
    """Approvers publish; editors too when the project lets them (ADR 0029)."""
    if access.can(Permission.DECIDE_VERSIONS):
        return True
    return (
        connection is not None
        and connection.publishers == "approvers_and_editors"
        and access.can(Permission.EDIT_BACKLOG)
    )


def require_publisher(access: ProjectAccess, connection: JiraConnection | None) -> None:
    access.require_member()
    if not can_publish(access, connection):
        raise PermissionDeniedError(
            "Only an Approver can publish to Jira in this project. An Approver can let Editors "
            "publish too, in Project settings."
        )


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
    notices: JiraNotices


def preview(context: PublishContext, access: ProjectAccess, version_id: UUID) -> Plan:
    """What publishing the version would do now. Calls nothing in Jira."""
    require_publisher(access, context.connections.connection(access.project_id))
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
    require_publisher(access, context.connections.connection(access.project_id))
    replayed = context.publishes.publish_by_key(access.project_id, idempotency_key)
    if replayed is not None:
        return replayed
    _usable(_connection(context.connections, access.project_id), now)
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
        _record_outcome(context, publish, entries, now)
    return publish


def view(context: PublishContext, access: ProjectAccess, publish: Publish) -> list[OutboxEntry]:
    require_publisher(access, context.connections.connection(access.project_id))
    return context.publishes.entries(publish.id)


def recent(context: PublishContext, access: ProjectAccess) -> list[Publish]:
    require_publisher(access, context.connections.connection(access.project_id))
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
    """Sends the next entries now, for someone allowed to publish. While the background sender
    holds the publish, or Jira asked to wait, it returns the publish as it is."""
    require_publisher(access, context.connections.connection(publish.project_id))
    claimed = context.publishes.claim_publish(publish.id, now(), now() + LEASE)
    if claimed is None:
        return context.publishes.publish(publish.id) or publish
    checkpoint()
    return _release(context, send_batch(context, claimed, checkpoint, now))


def send_due(
    context: PublishContext, checkpoint: Checkpoint, now: Callable[[], datetime]
) -> Publish | None:
    """The background sender's step: claims one publish that is due and sends its next entries.
    None when nothing is due. Two senders never hold the same publish: the claim is one
    conditional update, and its lease expires if the sender holding it dies (ADR 0029)."""
    claimed = context.publishes.claim_due_publish(now(), now() + LEASE)
    if claimed is None:
        return None
    checkpoint()
    return _release(context, send_batch(context, claimed, checkpoint, now))


def send_batch(
    context: PublishContext,
    publish: Publish,
    checkpoint: Checkpoint,
    now: Callable[[], datetime],
) -> Publish:
    """Sends the next entries in order, as the publish's starter. A rate limit or an unreachable
    Jira stops early and sets when to try again; an item Jira refuses, or one sent too often
    without an answer, is marked failed and the rest go on. When nothing is left, the publish
    is done, or failed if any item failed."""
    if publish.status != "sending":
        return publish
    if publish.next_attempt_at is not None and publish.next_attempt_at > now():
        return publish
    connection = context.connections.connection(publish.project_id)
    if connection is None:
        failed = replace(
            publish,
            status="failed",
            finished_at=now(),
            last_error=JiraNotConnectedError.code,
            next_attempt_at=None,
            revision=publish.revision + 1,
        )
        context.publishes.save_publish(failed)
        _record_outcome(context, failed, context.publishes.entries(publish.id), now())
        return failed
    try:
        _usable(connection, now())
    except DomainError as error:
        return _fail_unsent(context, publish, error.code, now())
    cipher = require_cipher(context.cipher)
    gateway = context.open_gateway(
        connection.site_url, connection.email, cipher.decrypt(connection.token_ciphertext)
    )
    entries = context.publishes.entries(publish.id)
    waiting = [entry for entry in entries if entry.state in ("pending", "sending")]
    stopped: DomainError | None = None
    sent = 0
    for entry in waiting[:ENTRIES_PER_ADVANCE]:
        if entry.attempts >= MAX_ENTRY_ATTEMPTS:
            context.publishes.save_entry(entry.failed(JiraUnavailableError.code))
            checkpoint()
            continue
        try:
            _send(context, connection, gateway, entry, checkpoint)
            sent += 1
        except (JiraRateLimitedError, JiraUnavailableError) as error:
            stopped = error
            break
        except DomainError as error:
            if error.code not in ITEM_FAILURES:
                if isinstance(error, JiraAuthFailedError):
                    context.connections.save_connection(connection.rejected(now()))
                    error = JiraTokenRejectedError(error.message)
                # Jira refused the account or the project: nothing else would get through.
                for left in context.publishes.entries(publish.id):
                    if left.state in ("pending", "sending"):
                        context.publishes.save_entry(left.failed(error.code))
                stopped = error
                break
            context.publishes.save_entry(entry.failed(error.code))
        checkpoint()
    entries = context.publishes.entries(publish.id)
    moved = replace(
        publish,
        last_error=None if stopped is None else stopped.code,
        failed_attempts=0 if stopped is None or sent else publish.failed_attempts + 1,
        revision=publish.revision + 1,
    )
    if isinstance(stopped, (JiraRateLimitedError, JiraUnavailableError)):
        retry_after = stopped.details.get("retry_after_seconds")
        moved = replace(
            moved,
            next_attempt_at=backoff(
                moved.failed_attempts or 1,
                retry_after if isinstance(retry_after, int) else None,
                now(),
            ),
        )
    else:
        moved = replace(moved, next_attempt_at=None)
    finished = finish(moved, entries, now())
    if finished.status != "sending":
        finished = replace(finished, last_error=None if stopped is None else stopped.code)
        _record_outcome(context, finished, entries, now())
    context.publishes.save_publish(finished)
    return finished


def _fail_unsent(context: PublishContext, publish: Publish, code: str, now: datetime) -> Publish:
    """Fails what is left without calling Jira, for a token known not to work. A retry after
    connecting again sends it."""
    for entry in context.publishes.entries(publish.id):
        if entry.state in ("pending", "sending"):
            context.publishes.save_entry(entry.failed(code))
    entries = context.publishes.entries(publish.id)
    failed = replace(finish(replace(publish, next_attempt_at=None), entries, now), last_error=code)
    context.publishes.save_publish(failed)
    _record_outcome(context, failed, entries, now)
    return failed


def _usable(connection: JiraConnection, now: datetime) -> None:
    """Refuses a token Jira has refused, or whose expiry date has passed."""
    state = connection.token_state(now.date())
    if state == "rejected":
        raise JiraTokenRejectedError(
            "Jira stopped accepting the saved API token; it may have expired or been revoked. "
            "An Approver needs to connect Jira again with a new token."
        )
    if state == "expired":
        raise JiraTokenExpiredError(
            "The Jira API token has expired. An Approver needs to make a new one and connect "
            "Jira again."
        )


def _release(context: PublishContext, publish: Publish) -> Publish:
    released = replace(publish, leased_until=None)
    context.publishes.save_publish(released)
    return released


def retry(
    context: PublishContext, access: ProjectAccess, publish: Publish, now: datetime
) -> Publish:
    """Sends the failed entries again; what was created stays and is never created twice."""
    require_publisher(access, context.connections.connection(publish.project_id))
    if publish.status != "failed":
        raise PublishNotRetryableError("Only a publish that failed can be tried again.")
    unfinished = context.publishes.unfinished_publish(publish.project_id)
    if unfinished is not None:
        raise PublishInProgressError(
            "Another publish to Jira is still going. Let it finish first.",
            details={"publish_id": str(unfinished.id)},
        )
    _usable(_connection(context.connections, publish.project_id), now)
    for entry in context.publishes.entries(publish.id):
        if entry.state == "failed":
            context.publishes.save_entry(
                replace(entry, state="pending", error_code=None, attempts=0)
            )
    retried = replace(
        publish,
        status="sending",
        finished_at=None,
        last_error=None,
        next_attempt_at=None,
        failed_attempts=0,
        revision=publish.revision + 1,
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
    context: PublishContext, publish: Publish, entries: list[OutboxEntry], now: datetime
) -> None:
    """The activity log and the person who started it hear about the outcome, in the same
    transaction as the outcome itself."""
    done = publish.status == "done"
    # Ids, counts and codes only: never titles, tokens or what Jira answered.
    logger.info(
        "Jira publish %s %s: %s",
        publish.id,
        publish.status,
        outcome_summary(entries),
        extra={"publish_id": str(publish.id), "status": publish.status},
    )
    context.notices.publish_finished(publish, outcome_counts(entries), now)
    context.audit.record(
        project_id=publish.project_id,
        actor=AuditActor.user(Actor(publish.created_by, publish.created_by_name)),
        type=EventType.JIRA_PUBLISHED if done else EventType.JIRA_PUBLISH_FAILED,
        subjects=[Subject(SubjectKind.BACKLOG_VERSION, publish.version_id)],
        summary=("Published to Jira: " if done else "Publishing to Jira stopped: ")
        + outcome_summary(entries),
        occurred_at=now,
    )
