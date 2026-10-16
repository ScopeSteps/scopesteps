"""People named in a project's sources: storing what a run extracted, listing, correcting a name
or role, and confirming decision rights the sources do not state.

Any project member lists; correcting and confirming need the editor role, like every other edit.
The agent never calls the correcting or confirming use cases.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.identity.client import ProjectAccess, Role
from scopesteps.kernel.errors import InvalidInputError, NotFoundError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.application.receipts import (
    Receipt,
    ReceiptStore,
    fingerprint,
    replayed_project,
)
from scopesteps.projects.domain.extraction import (
    MAX_PEOPLE_PER_RUN,
    ExtractedPerson,
    extraction_problems,
    name_key,
)
from scopesteps.projects.domain.ids import PersonId, ProjectId
from scopesteps.projects.domain.person import ConfirmedRights, Person, PersonChangedError

# Audit summaries name no person: the name comes from the sources or the model, and the event's
# subject id lets a reader look the person up under this module's rules.
_RIGHTS_SUMMARIES: dict[ConfirmedRights, str] = {
    "decides": "Confirmed that a person decides scope",
    "advises": "Confirmed that a person advises on scope",
    "unknown": "Recorded a person's decision rights as unknown",
}


class PeopleStore(Protocol):
    """Persistence for people. Writes join the caller's transaction; the caller commits."""

    def in_project(self, project_id: ProjectId) -> list[Person]:
        """The project's people, oldest first."""
        ...

    def get(self, person_id: PersonId) -> Person | None: ...

    def add(self, person: Person) -> None: ...

    def save(self, person: Person, *, expected_revision: int) -> bool:
        """Compare-and-set: False, and nothing written, if the stored revision has moved on."""
        ...


def record_extracted_people(
    store: PeopleStore,
    project_id: ProjectId,
    run_id: UUID,
    people: Sequence[ExtractedPerson],
    now: datetime,
) -> None:
    """Store a run's people without committing; the caller owns the transaction.

    A reading that names the participant it is about (`person_id`, set when the run read a
    confirmed speaker) is stored on that participant. Otherwise matching is by name, in this
    order: a person whose extracted name is the same, then a person whose entered or corrected
    name is the same. Names are compared with `name_key`. A match
    gets the new reading and keeps its correction, confirmed rights, entered name and meeting
    role; anyone else is added. People a run does not mention stay as they are, because a later
    run may read fewer sources.
    """
    problems = [problem for person in people for problem in extraction_problems(person)]
    if len(people) > MAX_PEOPLE_PER_RUN:
        problems.append(f"more than {MAX_PEOPLE_PER_RUN} people")
    if problems:
        raise InvalidInputError(
            "The extracted people cannot be stored", details={"problems": problems}
        )
    known = store.in_project(project_id)
    seen: set[str] = set()
    for extracted in people:
        key = name_key(extracted.name)
        if key in seen:
            continue
        seen.add(key)
        match = (
            next((person for person in known if person.id == extracted.person_id), None)
            or next(
                (
                    person
                    for person in known
                    if person.extracted is not None and name_key(person.extracted.name) == key
                ),
                None,
            )
            or next((person for person in known if person.is_named(key)), None)
        )
        if match is None:
            store.add(
                Person(
                    id=PersonId(new_id()),
                    project_id=project_id,
                    revision=1,
                    origin="extracted",
                    extracted=extracted,
                    run_id=run_id,
                    extracted_at=now,
                    created_at=now,
                )
            )
            continue
        # One stored person takes at most one reading per run.
        known = [person for person in known if person.id != match.id]
        updated = match.re_extracted(extracted, run_id, now)
        if not store.save(updated, expected_revision=match.revision):
            raise PersonChangedError("A person changed while the run's people were being saved")


def list_people(store: PeopleStore, access: ProjectAccess) -> list[Person]:
    access.require_member()
    return store.in_project(access.project_id)


@dataclass(frozen=True)
class CorrectPerson:
    idempotency_key: str
    person_id: PersonId
    expected_revision: int
    name: str | None
    role: str | None
    """None keeps the agent's value for that field."""


def correct_person(
    store: PeopleStore,
    receipts: ReceiptStore,
    audit: AuditRecorder,
    access: ProjectAccess,
    command: CorrectPerson,
    now: datetime,
) -> Person:
    """Replace the person's correction if `expected_revision` is still their revision.

    A retry with the same Idempotency-Key returns the person as they are now. A correction that
    leaves the shown name and role as they were changes nothing and records nothing.
    """
    access.require_role(Role.EDITOR)
    command_fingerprint = fingerprint(
        "person.correct",
        access.project_id,
        str(command.person_id),
        command.expected_revision,
        command.name,
        command.role,
    )
    if _replayed(receipts, access, command.idempotency_key, command_fingerprint):
        return _load(store, access, command.person_id)

    person = _current(store, access, command.person_id, command.expected_revision)
    updated = person.corrected(command.name, command.role, access.actor.user_id, now)
    changed = [
        field
        for field, before, after in (
            ("name", person.name, updated.name),
            ("role", person.role, updated.role),
        )
        if before != after
    ]
    if changed:
        _save(store, person, updated)
        audit.record(
            project_id=access.project_id,
            actor=AuditActor.user(access.actor),
            type=EventType.PERSON_CORRECTED,
            subjects=(Subject(SubjectKind.PERSON, person.id),),
            summary=f"Corrected a person's {' and '.join(changed)}",
            occurred_at=now,
        )
    else:
        updated = person
    _add_receipt(receipts, access, command.idempotency_key, command_fingerprint, now)
    return updated


@dataclass(frozen=True)
class ConfirmRights:
    idempotency_key: str
    person_id: PersonId
    expected_revision: int
    rights: ConfirmedRights


def confirm_rights(
    store: PeopleStore,
    receipts: ReceiptStore,
    audit: AuditRecorder,
    access: ProjectAccess,
    command: ConfirmRights,
    now: datetime,
) -> Person:
    """Set the person's confirmed decision rights if `expected_revision` is still their revision.

    Refused when a source states the rights. A retry with the same Idempotency-Key returns the
    person as they are now; confirming the value already confirmed changes nothing.
    """
    access.require_role(Role.EDITOR)
    command_fingerprint = fingerprint(
        "person.confirm_rights",
        access.project_id,
        str(command.person_id),
        command.expected_revision,
        command.rights,
    )
    if _replayed(receipts, access, command.idempotency_key, command_fingerprint):
        return _load(store, access, command.person_id)

    person = _current(store, access, command.person_id, command.expected_revision)
    updated = person.with_confirmed_rights(command.rights, access.actor.user_id, now)
    already = (
        person.confirmed_rights is not None and person.confirmed_rights.rights == command.rights
    )
    if already:
        updated = person
    else:
        _save(store, person, updated)
        audit.record(
            project_id=access.project_id,
            actor=AuditActor.user(access.actor),
            type=EventType.PERSON_RIGHTS_CONFIRMED,
            subjects=(Subject(SubjectKind.PERSON, person.id),),
            summary=_RIGHTS_SUMMARIES[command.rights],
            occurred_at=now,
        )
    _add_receipt(receipts, access, command.idempotency_key, command_fingerprint, now)
    return updated


def _load(store: PeopleStore, access: ProjectAccess, person_id: PersonId) -> Person:
    person = store.get(person_id)
    # A person of another project is reported exactly like a missing one.
    if person is None or person.project_id != access.project_id:
        raise NotFoundError("Person not found")
    return person


def _current(
    store: PeopleStore, access: ProjectAccess, person_id: PersonId, expected_revision: int
) -> Person:
    person = _load(store, access, person_id)
    if person.revision != expected_revision:
        raise PersonChangedError(
            "This person changed since you loaded them. Reload and try again.",
            details={"current_revision": person.revision},
        )
    return person


def _save(store: PeopleStore, person: Person, updated: Person) -> None:
    if not store.save(updated, expected_revision=person.revision):
        raise PersonChangedError("This person changed while saving. Reload and try again.")


def _replayed(
    receipts: ReceiptStore, access: ProjectAccess, idempotency_key: str, command_fingerprint: str
) -> bool:
    return (
        replayed_project(receipts, access.actor.user_id, idempotency_key, command_fingerprint)
        is not None
    )


def _add_receipt(
    receipts: ReceiptStore,
    access: ProjectAccess,
    idempotency_key: str,
    command_fingerprint: str,
    now: datetime,
) -> None:
    receipts.add(
        Receipt(access.actor.user_id, idempotency_key, access.project_id, command_fingerprint, now)
    )
