"""Who's who in a project's transcripts: listing each speaker with what is known about them, and
saving an editor's whole answer for one transcript (ADR 0012).

Labels come from `sources` through `SpeakerLabelReader`; this module never reads source text.
Any member lists; saving needs the editor role. Saving never blocks or starts a run.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.identity.client import ProjectAccess, Role, UserId
from scopesteps.kernel.errors import InvalidInputError, NotFoundError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.application.people import PeopleStore
from scopesteps.projects.application.receipts import (
    Receipt,
    ReceiptStore,
    fingerprint,
    replayed_project,
)
from scopesteps.projects.domain.extraction import name_key
from scopesteps.projects.domain.ids import PersonId, ProjectId
from scopesteps.projects.domain.person import (
    Person,
    PersonChangedError,
    meeting_role_value,
    participant_name,
)
from scopesteps.projects.domain.speakers import (
    Assignment,
    ResolvedSpeaker,
    SpeakerMapping,
    SpeakersChangedError,
    TranscriptSpeakers,
    resolve_speakers,
)


class ParticipantExistsError(InvalidInputError):
    code = "PARTICIPANT_EXISTS"


class SpeakerLabelReader(Protocol):
    def __call__(self, project_id: ProjectId) -> list[TranscriptSpeakers]:
        """The labels in each of the project's current transcripts, in source order."""
        ...


class SpeakerMappingStore(Protocol):
    """Writes join the caller's transaction; the caller commits."""

    def mappings(self, project_id: ProjectId) -> list[SpeakerMapping]:
        """Every source's mapping in the project that has ever been saved."""
        ...

    def save(
        self, project_id: ProjectId, mapping: SpeakerMapping, *, expected_revision: int
    ) -> bool:
        """Compare-and-set on the source's revision: False, and nothing written, if it moved."""
        ...


@dataclass(frozen=True)
class TranscriptView:
    transcript: TranscriptSpeakers
    revision: int
    speakers: list[ResolvedSpeaker]


@dataclass(frozen=True)
class LinkParticipant:
    person_id: PersonId
    meeting_role: str | None
    """None leaves the participant's meeting role as it is; a blank one clears it."""


@dataclass(frozen=True)
class NewParticipant:
    name: str
    meeting_role: str | None


@dataclass(frozen=True)
class NotAPerson:
    pass


SpeakerChoice = LinkParticipant | NewParticipant | NotAPerson


@dataclass(frozen=True)
class AssignSpeakers:
    """The whole answer for one transcript: a label left out goes back to unconfirmed."""

    idempotency_key: str
    source_id: UUID
    expected_revision: int
    choices: tuple[tuple[str, SpeakerChoice], ...]


def project_speakers(
    people: PeopleStore,
    mappings: SpeakerMappingStore,
    labels: SpeakerLabelReader,
    project_id: ProjectId,
) -> list[TranscriptView]:
    """Every current transcript's speakers with what is known about each. No access check."""
    stored = {mapping.source_id: mapping for mapping in mappings.mappings(project_id)}
    known = people.in_project(project_id)
    return [
        TranscriptView(
            transcript=transcript,
            revision=_mapping(stored, transcript.source_id).revision,
            speakers=resolve_speakers(
                transcript, _mapping(stored, transcript.source_id), stored.values(), known
            ),
        )
        for transcript in labels(project_id)
    ]


def list_speakers(
    people: PeopleStore,
    mappings: SpeakerMappingStore,
    labels: SpeakerLabelReader,
    access: ProjectAccess,
) -> list[TranscriptView]:
    access.require_member()
    return project_speakers(people, mappings, labels, access.project_id)


def assign_speakers(
    people: PeopleStore,
    mappings: SpeakerMappingStore,
    labels: SpeakerLabelReader,
    receipts: ReceiptStore,
    audit: AuditRecorder,
    access: ProjectAccess,
    command: AssignSpeakers,
    now: datetime,
) -> TranscriptView:
    """Save the editor's answer for one transcript if `expected_revision` is still its revision.

    Linking two labels to one participant is allowed. A new participant whose name a person on
    the project already answers to is refused: link that person instead. A retry with the same
    Idempotency-Key returns the transcript as it is now; an answer that changes nothing records
    nothing and keeps the revision.
    """
    access.require_role(Role.EDITOR)
    command_fingerprint = fingerprint(
        "speakers.assign",
        access.project_id,
        str(command.source_id),
        command.expected_revision,
        json.dumps([[key, _choice_json(choice)] for key, choice in command.choices]),
    )
    if replayed_project(
        receipts, access.actor.user_id, command.idempotency_key, command_fingerprint
    ):
        return _view(people, mappings, labels, access.project_id, command.source_id)

    transcript = _transcript(labels, access.project_id, command.source_id)
    stored = {mapping.source_id: mapping for mapping in mappings.mappings(access.project_id)}
    current = _mapping(stored, command.source_id)
    if current.revision != command.expected_revision:
        raise SpeakersChangedError(
            "Someone changed who's who in this transcript since you loaded it. Reload and "
            "try again.",
            details={"current_revision": current.revision},
        )

    known = people.in_project(access.project_id)
    plan = _plan(command.choices, transcript, known)
    by, created, roles_changed = access.actor.user_id, 0, 0
    person_for_name: dict[str, PersonId] = {}
    answers: list[Assignment] = []
    for key, choice in plan:
        match choice:
            case NotAPerson():
                person_id = None
            case NewParticipant(name=name, meeting_role=role):
                person_id = person_for_name.get(name_key(name))
                if person_id is None:
                    person = Person.confirmed_speaker(
                        PersonId(new_id()), access.project_id, name, role, by, now
                    )
                    people.add(person)
                    created += 1
                    person_id = person_for_name[name_key(name)] = person.id
            case LinkParticipant(person_id=person_id, meeting_role=role):
                if role is not None:
                    roles_changed += _set_meeting_role(people, person_id, role, by, now)
        previous = current.assignment(key)
        if previous is None or previous.person_id != person_id:
            previous = Assignment(key, person_id, by, now, current.revision + 1)
        answers.append(previous)

    if set(answers) == set(current.assignments) and not created and not roles_changed:
        _add_receipt(receipts, access, command.idempotency_key, command_fingerprint, now)
        return _view(people, mappings, labels, access.project_id, command.source_id)

    saved = SpeakerMapping(command.source_id, current.revision + 1, tuple(answers))
    if not mappings.save(access.project_id, saved, expected_revision=current.revision):
        raise SpeakersChangedError(
            "Someone changed who's who in this transcript while saving. Reload and try again."
        )
    audit.record(
        project_id=access.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.SPEAKERS_CONFIRMED,
        subjects=(
            Subject(SubjectKind.SOURCE, command.source_id),
            *(
                Subject(SubjectKind.PERSON, person_id)
                for person_id in dict.fromkeys(a.person_id for a in answers if a.person_id)
            ),
        ),
        summary=_summary(answers, created),
        occurred_at=now,
    )
    _add_receipt(receipts, access, command.idempotency_key, command_fingerprint, now)
    return _view(people, mappings, labels, access.project_id, command.source_id)


def _plan(
    choices: Sequence[tuple[str, SpeakerChoice]],
    transcript: TranscriptSpeakers,
    known: Sequence[Person],
) -> list[tuple[str, SpeakerChoice]]:
    """The choices with names and roles cleaned, checked against the transcript and the people."""
    keys = {label.key for label in transcript.labels}
    known_ids = {person.id for person in known}
    roles: dict[PersonId, str | None] = {}
    seen: set[str] = set()
    plan: list[tuple[str, SpeakerChoice]] = []
    for index, (key, choice) in enumerate(choices):
        field = f"speakers[{index}]"
        if key not in keys:
            raise InvalidInputError(
                "This transcript has no speaker with that label",
                details={"field": f"{field}.label_key"},
            )
        if key in seen:
            raise InvalidInputError(
                "A label can be answered only once", details={"field": f"{field}.label_key"}
            )
        seen.add(key)
        match choice:
            case NotAPerson():
                plan.append((key, choice))
            case NewParticipant(name=name, meeting_role=role):
                name = participant_name(name, f"{field}.name")
                existing = next((p for p in known if p.is_named(name_key(name))), None)
                if existing is not None:
                    raise ParticipantExistsError(
                        "A participant with this name is already on the project; choose them "
                        "instead",
                        details={"field": f"{field}.name", "person_id": str(existing.id)},
                    )
                role = None if role is None else meeting_role_value(role, f"{field}.meeting_role")
                plan.append((key, NewParticipant(name, role)))
            case LinkParticipant(person_id=person_id, meeting_role=role):
                if person_id not in known_ids:
                    raise InvalidInputError(
                        "No such participant on this project",
                        details={"field": f"{field}.person_id"},
                    )
                if role is not None:
                    cleaned = meeting_role_value(role, f"{field}.meeting_role")
                    if roles.setdefault(person_id, cleaned) != cleaned:
                        raise InvalidInputError(
                            "One participant was given two different meeting roles",
                            details={"field": f"{field}.meeting_role"},
                        )
                    role = cleaned or ""
                plan.append((key, LinkParticipant(person_id, role)))
    return plan


def _set_meeting_role(
    people: PeopleStore, person_id: PersonId, role: str, by: UserId, at: datetime
) -> int:
    """Set a linked participant's meeting role; an empty one clears it. 1 if it changed."""
    person = people.get(person_id)
    if person is None:
        raise NotFoundError("Person not found")
    updated = person.with_meeting_role(role or None, by, at)
    if updated is person:
        return 0
    if not people.save(updated, expected_revision=person.revision):
        raise PersonChangedError("A participant changed while saving. Reload and try again.")
    return 1


def _summary(answers: Sequence[Assignment], created: int) -> str:
    # Counts only: names come from the transcript or an editor (see the people summaries).
    linked = sum(1 for answer in answers if answer.person_id is not None)
    not_people = len(answers) - linked
    parts = [f"{linked} {'speaker' if linked == 1 else 'speakers'} linked"]
    if created:
        parts.append(f"{created} new {'participant' if created == 1 else 'participants'}")
    if not_people:
        parts.append(f"{not_people} not a person")
    return "Confirmed who's who in a transcript: " + ", ".join(parts)


def _choice_json(choice: SpeakerChoice) -> list[str | None]:
    match choice:
        case NotAPerson():
            return ["not_a_person"]
        case NewParticipant(name=name, meeting_role=role):
            return ["new", name, role]
        case LinkParticipant(person_id=person_id, meeting_role=role):
            return ["link", str(person_id), role]


def _transcript(
    labels: SpeakerLabelReader, project_id: ProjectId, source_id: UUID
) -> TranscriptSpeakers:
    found = next((t for t in labels(project_id) if t.source_id == source_id), None)
    # Another project's source, a removed one and one that is not a transcript all look missing.
    if found is None:
        raise NotFoundError("Transcript not found")
    return found


def _view(
    people: PeopleStore,
    mappings: SpeakerMappingStore,
    labels: SpeakerLabelReader,
    project_id: ProjectId,
    source_id: UUID,
) -> TranscriptView:
    views = project_speakers(people, mappings, labels, project_id)
    found = next((view for view in views if view.transcript.source_id == source_id), None)
    if found is None:
        raise NotFoundError("Transcript not found")
    return found


def _mapping(stored: dict[UUID, SpeakerMapping], source_id: UUID) -> SpeakerMapping:
    return stored.get(source_id) or SpeakerMapping(source_id, 0, ())


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
