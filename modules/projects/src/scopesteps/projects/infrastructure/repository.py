from collections.abc import Collection
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from scopesteps.identity.client import UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.application.projects import Receipt
from scopesteps.projects.domain.ids import ProjectId
from scopesteps.projects.domain.project import Project
from scopesteps.projects.infrastructure.orm import CommandReceiptRecord, ProjectRecord


class SqlProjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, project_id: ProjectId) -> Project | None:
        record = self._session.get(ProjectRecord, project_id, populate_existing=True)
        return None if record is None else _to_project(record)

    def get_many(self, project_ids: Collection[ProjectId]) -> list[Project]:
        records = self._session.scalars(
            select(ProjectRecord).where(ProjectRecord.id.in_(list(project_ids)))
        )
        return [_to_project(record) for record in records]

    def add(self, project: Project) -> None:
        self._session.add(
            ProjectRecord(
                id=project.id,
                name=project.name,
                revision=project.revision,
                created_at=project.created_at,
            )
        )
        # Rows in other tables written later in the transaction reference the project.
        self._session.flush()

    def rename(self, project_id: ProjectId, name: str, *, expected_revision: int) -> bool:
        # The revision is compared in the UPDATE itself, so of two writers holding the same
        # revision exactly one succeeds.
        result = self._session.execute(
            update(ProjectRecord)
            .where(ProjectRecord.id == project_id, ProjectRecord.revision == expected_revision)
            .values(name=name, revision=expected_revision + 1)
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1


class SqlReceiptStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, actor_id: UserId, idempotency_key: str) -> Receipt | None:
        record = self._session.scalars(
            select(CommandReceiptRecord).where(
                CommandReceiptRecord.actor_id == actor_id,
                CommandReceiptRecord.idempotency_key == idempotency_key,
            )
        ).one_or_none()
        if record is None:
            return None
        return Receipt(
            actor_id=UserId(record.actor_id),
            idempotency_key=record.idempotency_key,
            project_id=ProjectId(record.project_id),
            fingerprint=record.fingerprint,
            created_at=record.created_at,
        )

    def add(self, receipt: Receipt) -> None:
        self._session.add(
            CommandReceiptRecord(
                id=new_id(),
                actor_id=receipt.actor_id,
                idempotency_key=receipt.idempotency_key,
                project_id=receipt.project_id,
                fingerprint=receipt.fingerprint,
                created_at=receipt.created_at,
            )
        )


def _to_project(record: ProjectRecord) -> Project:
    return Project(
        id=ProjectId(record.id),
        name=record.name,
        created_at=record.created_at,
        revision=record.revision,
    )
