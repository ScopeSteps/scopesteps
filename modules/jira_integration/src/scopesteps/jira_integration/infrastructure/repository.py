from dataclasses import asdict
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from scopesteps.identity.client import UserId
from scopesteps.jira_integration.domain.connection import IssueTypes, JiraConnection, JiraProject
from scopesteps.jira_integration.domain.ids import OutboxEntryId, PublishId
from scopesteps.jira_integration.domain.plan import IssueContent, IssueKind, IssueLink, Operation
from scopesteps.jira_integration.domain.publish import (
    EntryState,
    OutboxEntry,
    Publish,
    PublishStatus,
)
from scopesteps.jira_integration.infrastructure.orm import (
    ConnectionRecord,
    IssueLinkRecord,
    OutboxEntryRecord,
    PublishRecord,
)
from scopesteps.projects.client import ProjectId


class SqlJiraStore:
    """Connections, publishes with their outbox entries, and issue links, in one session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def connection(self, project_id: ProjectId) -> JiraConnection | None:
        record = self._session.get(ConnectionRecord, project_id)
        return None if record is None else _to_connection(record)

    def save_connection(self, connection: JiraConnection) -> None:
        project = connection.jira_project
        self._session.merge(
            ConnectionRecord(
                project_id=connection.project_id,
                site_url=connection.site_url,
                email=connection.email,
                token_ciphertext=connection.token_ciphertext,
                jira_project_id=project.id,
                jira_project_key=project.key,
                jira_project_name=project.name,
                epic_type_id=project.issue_types.epic,
                story_type_id=project.issue_types.story,
                subtask_type_id=project.issue_types.subtask,
                auto_publish=connection.auto_publish,
                revision=connection.revision,
                connected_by=connection.connected_by,
                connected_at=connection.connected_at,
                checked_at=connection.checked_at,
            )
        )
        self._session.flush()

    def delete_connection(self, project_id: ProjectId) -> None:
        self._session.execute(
            delete(ConnectionRecord).where(ConnectionRecord.project_id == project_id)
        )

    def forget_links(self, project_id: ProjectId) -> None:
        self._session.execute(
            delete(IssueLinkRecord).where(IssueLinkRecord.project_id == project_id)
        )

    def publish(self, publish_id: PublishId) -> Publish | None:
        record = self._session.get(PublishRecord, publish_id)
        return None if record is None else _to_publish(record)

    def publish_by_key(self, project_id: ProjectId, idempotency_key: str) -> Publish | None:
        record = self._session.scalars(
            select(PublishRecord).where(
                PublishRecord.project_id == project_id,
                PublishRecord.idempotency_key == idempotency_key,
            )
        ).one_or_none()
        return None if record is None else _to_publish(record)

    def unfinished_publish(self, project_id: ProjectId) -> Publish | None:
        record = self._session.scalars(
            select(PublishRecord)
            .where(PublishRecord.project_id == project_id, PublishRecord.status == "sending")
            .order_by(PublishRecord.created_at, PublishRecord.id)
            .limit(1)
        ).one_or_none()
        return None if record is None else _to_publish(record)

    def recent_publishes(self, project_id: ProjectId, limit: int) -> list[Publish]:
        records = self._session.scalars(
            select(PublishRecord)
            .where(PublishRecord.project_id == project_id)
            .order_by(PublishRecord.created_at.desc(), PublishRecord.id.desc())
            .limit(limit)
        )
        return [_to_publish(record) for record in records]

    def add_publish(self, publish: Publish, entries: list[OutboxEntry]) -> None:
        self._session.add(PublishRecord(**_publish_fields(publish)))
        self._session.flush()
        self._session.add_all(OutboxEntryRecord(**_entry_fields(entry)) for entry in entries)
        self._session.flush()

    def save_publish(self, publish: Publish) -> None:
        self._session.merge(PublishRecord(**_publish_fields(publish)))
        self._session.flush()

    def entries(self, publish_id: PublishId) -> list[OutboxEntry]:
        records = self._session.scalars(
            select(OutboxEntryRecord)
            .where(OutboxEntryRecord.publish_id == publish_id)
            .order_by(OutboxEntryRecord.position)
        )
        return [_to_entry(record) for record in records]

    def save_entry(self, entry: OutboxEntry) -> None:
        self._session.merge(OutboxEntryRecord(**_entry_fields(entry)))
        self._session.flush()

    def links(self, project_id: ProjectId) -> dict[UUID, IssueLink]:
        records = self._session.scalars(
            select(IssueLinkRecord).where(IssueLinkRecord.project_id == project_id)
        )
        return {
            record.item_id: IssueLink(
                item_id=record.item_id,
                kind=cast(IssueKind, record.kind),
                jira_key=record.jira_key,
                jira_id=record.jira_id,
                fingerprint=record.fingerprint,
                closed=record.closed,
            )
            for record in records
        }

    def save_link(self, project_id: ProjectId, link: IssueLink) -> None:
        self._session.merge(
            IssueLinkRecord(
                project_id=project_id,
                item_id=link.item_id,
                kind=link.kind,
                jira_key=link.jira_key,
                jira_id=link.jira_id,
                fingerprint=link.fingerprint,
                closed=link.closed,
            )
        )
        self._session.flush()


def _to_connection(record: ConnectionRecord) -> JiraConnection:
    return JiraConnection(
        project_id=ProjectId(record.project_id),
        site_url=record.site_url,
        email=record.email,
        token_ciphertext=record.token_ciphertext,
        jira_project=JiraProject(
            id=record.jira_project_id,
            key=record.jira_project_key,
            name=record.jira_project_name,
            issue_types=IssueTypes(
                epic=record.epic_type_id,
                story=record.story_type_id,
                subtask=record.subtask_type_id,
            ),
        ),
        auto_publish=record.auto_publish,
        revision=record.revision,
        connected_by=UserId(record.connected_by),
        connected_at=record.connected_at,
        checked_at=record.checked_at,
    )


def _publish_fields(publish: Publish) -> dict[str, Any]:
    return {
        "id": publish.id,
        "project_id": publish.project_id,
        "version_id": publish.version_id,
        "idempotency_key": publish.idempotency_key,
        "status": publish.status,
        "created_by": publish.created_by,
        "created_by_name": publish.created_by_name,
        "created_at": publish.created_at,
        "finished_at": publish.finished_at,
        "last_error": publish.last_error,
        "revision": publish.revision,
    }


def _to_publish(record: PublishRecord) -> Publish:
    return Publish(
        id=PublishId(record.id),
        project_id=ProjectId(record.project_id),
        version_id=record.version_id,
        idempotency_key=record.idempotency_key,
        status=cast(PublishStatus, record.status),
        created_by=UserId(record.created_by),
        created_by_name=record.created_by_name,
        created_at=record.created_at,
        finished_at=record.finished_at,
        last_error=record.last_error,
        revision=record.revision,
    )


def _entry_fields(entry: OutboxEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "publish_id": entry.publish_id,
        "position": entry.position,
        "item_id": entry.item_id,
        "kind": entry.kind,
        "operation": entry.operation,
        "content": None if entry.content is None else _content_json(entry.content),
        "jira_key": entry.jira_key,
        "state": entry.state,
        "error_code": entry.error_code,
        "attempts": entry.attempts,
    }


def _content_json(content: IssueContent) -> dict[str, Any]:
    fields = asdict(content)
    fields["item_id"] = str(content.item_id)
    fields["parent_item_id"] = (
        None if content.parent_item_id is None else str(content.parent_item_id)
    )
    return fields


def _to_entry(record: OutboxEntryRecord) -> OutboxEntry:
    content = record.content
    return OutboxEntry(
        id=OutboxEntryId(record.id),
        publish_id=PublishId(record.publish_id),
        position=record.position,
        item_id=record.item_id,
        kind=cast(IssueKind, record.kind),
        operation=cast(Operation, record.operation),
        content=None if content is None else _to_content(content),
        jira_key=record.jira_key,
        state=cast(EntryState, record.state),
        error_code=record.error_code,
        attempts=record.attempts,
    )


def _to_content(fields: dict[str, Any]) -> IssueContent:
    parent = fields["parent_item_id"]
    return IssueContent(
        item_id=UUID(fields["item_id"]),
        kind=fields["kind"],
        parent_item_id=None if parent is None else UUID(parent),
        summary=fields["summary"],
        body=fields["body"],
        criteria=tuple(fields["criteria"]),
        assumptions=tuple(fields["assumptions"]),
        open_questions=tuple(fields["open_questions"]),
        link=fields["link"],
    )
