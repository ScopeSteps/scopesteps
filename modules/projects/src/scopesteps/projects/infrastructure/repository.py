from collections.abc import Collection
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from scopesteps.identity.client import UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.application.receipts import Receipt
from scopesteps.projects.domain.extraction import (
    ExtractedPerson,
    PersonEvidence,
    StatedRights,
    name_key,
)
from scopesteps.projects.domain.ids import PersonId, ProjectId
from scopesteps.projects.domain.person import (
    ConfirmedRights,
    Correction,
    Person,
    RightsConfirmation,
)
from scopesteps.projects.domain.project import Project
from scopesteps.projects.infrastructure.orm import CommandReceiptRecord, PersonRecord, ProjectRecord


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


class SqlPeopleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def in_project(self, project_id: ProjectId) -> list[Person]:
        # Ids are UUIDv7, so ordering by id is ordering by when a person was first extracted.
        records = self._session.scalars(
            select(PersonRecord)
            .where(PersonRecord.project_id == project_id)
            .order_by(PersonRecord.id)
            .execution_options(populate_existing=True)
        )
        return [_to_person(record) for record in records]

    def get(self, person_id: PersonId) -> Person | None:
        record = self._session.get(PersonRecord, person_id, populate_existing=True)
        return None if record is None else _to_person(record)

    def add(self, person: Person) -> None:
        self._session.add(PersonRecord(id=person.id, **_fields(person)))
        self._session.flush()

    def save(self, person: Person, *, expected_revision: int) -> bool:
        result = self._session.execute(
            update(PersonRecord)
            .where(PersonRecord.id == person.id, PersonRecord.revision == expected_revision)
            .values(**_fields(person))
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1


def _fields(person: Person) -> dict[str, Any]:
    extracted, correction, confirmed = person.extracted, person.correction, person.confirmed_rights
    return {
        "project_id": person.project_id,
        "name_key": name_key(extracted.name),
        "revision": person.revision,
        "extracted_name": extracted.name,
        "extracted_role": extracted.role,
        "extracted_said": extracted.said,
        "stated_rights": extracted.stated_rights,
        "evidence": [_evidence_json(e) for e in extracted.evidence],
        "rights_evidence": [_evidence_json(e) for e in extracted.rights_evidence],
        "run_id": person.run_id,
        "extracted_at": person.extracted_at,
        "corrected_name": correction.name if correction else None,
        "corrected_role": correction.role if correction else None,
        "corrected_by": correction.corrected_by if correction else None,
        "corrected_at": correction.corrected_at if correction else None,
        "confirmed_rights": confirmed.rights if confirmed else None,
        "rights_confirmed_by": confirmed.confirmed_by if confirmed else None,
        "rights_confirmed_at": confirmed.confirmed_at if confirmed else None,
        "created_at": person.created_at,
    }


def _to_person(record: PersonRecord) -> Person:
    correction = None
    if record.corrected_by is not None and record.corrected_at is not None:
        correction = Correction(
            name=record.corrected_name,
            role=record.corrected_role,
            corrected_by=UserId(record.corrected_by),
            corrected_at=record.corrected_at,
        )
    confirmed = None
    if (
        record.confirmed_rights is not None
        and record.rights_confirmed_by is not None
        and record.rights_confirmed_at is not None
    ):
        confirmed = RightsConfirmation(
            rights=_confirmed_rights(record.confirmed_rights),
            confirmed_by=UserId(record.rights_confirmed_by),
            confirmed_at=record.rights_confirmed_at,
        )
    return Person(
        id=PersonId(record.id),
        project_id=ProjectId(record.project_id),
        revision=record.revision,
        extracted=ExtractedPerson(
            name=record.extracted_name,
            role=record.extracted_role,
            said=record.extracted_said,
            stated_rights=_stated_rights(record.stated_rights),
            evidence=tuple(_evidence_from_json(e) for e in record.evidence),
            rights_evidence=tuple(_evidence_from_json(e) for e in record.rights_evidence),
        ),
        run_id=record.run_id,
        extracted_at=record.extracted_at,
        created_at=record.created_at,
        correction=correction,
        confirmed_rights=confirmed,
    )


def _evidence_json(evidence: PersonEvidence) -> dict[str, Any]:
    return {
        "source_version_id": str(evidence.source_version_id),
        "block_id": str(evidence.block_id),
        "quote": evidence.quote,
    }


def _evidence_from_json(data: dict[str, Any]) -> PersonEvidence:
    return PersonEvidence(UUID(data["source_version_id"]), UUID(data["block_id"]), data["quote"])


def _stated_rights(value: str) -> StatedRights:
    match value:
        case "decides" | "advises":
            return value
        case _:
            return "not_stated"


def _confirmed_rights(value: str) -> ConfirmedRights:
    match value:
        case "decides" | "advises":
            return value
        case _:
            return "unknown"


def _to_project(record: ProjectRecord) -> Project:
    return Project(
        id=ProjectId(record.id),
        name=record.name,
        created_at=record.created_at,
        revision=record.revision,
    )
