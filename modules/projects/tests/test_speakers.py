"""Who's who in transcripts against in-memory stores. All names are synthetic."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from scopesteps.audit.client import AuditActor, EventType, Subject, SubjectKind
from scopesteps.identity.client import Actor, ProjectAccess, Role, UserId
from scopesteps.kernel.errors import InvalidInputError, NotFoundError, PermissionDeniedError
from scopesteps.projects.application.people import record_extracted_people
from scopesteps.projects.application.receipts import IdempotencyKeyReusedError, Receipt
from scopesteps.projects.application.speakers import (
    AssignSpeakers,
    LinkParticipant,
    NewParticipant,
    NotAPerson,
    ParticipantExistsError,
    SpeakerChoice,
    TranscriptView,
    assign_speakers,
    list_speakers,
)
from scopesteps.projects.client import ExtractedPerson, PersonEvidence, PersonId, ProjectId
from scopesteps.projects.domain.person import Person
from scopesteps.projects.domain.speakers import (
    SpeakerLabel,
    SpeakerMapping,
    SpeakersChangedError,
    TranscriptSpeakers,
)

PROJECT = ProjectId(UUID("019a3a5e-0000-7000-8000-0000000000a1"))
OTHER_PROJECT = ProjectId(UUID("019a3a5e-0000-7000-8000-0000000000a2"))
EDITOR = Actor(user_id=UserId(UUID("019a3a5e-0000-7000-8000-0000000000b1")), display_name="Edit")
KICKOFF, FOLLOW_UP = UUID(int=101), UUID(int=102)
NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)
DANA = ExtractedPerson(
    name="Dana Ruiz",
    role="Facilities Manager",
    said="Wants a shorter maximum booking.",
    stated_rights="not_stated",
    evidence=(PersonEvidence(UUID(int=11), UUID(int=12), "Dana Ruiz"),),
)


def _label(name: str, turns: int = 1) -> SpeakerLabel:
    return SpeakerLabel(
        key=name.casefold(),
        label=name,
        turn_count=turns,
        first_block_id=UUID(int=500 + len(name)),
        first_paragraph=2,
        sample=f"{name} says hello.",
    )


class Fakes:
    """People, mappings, receipts and audit events, plus the transcripts `sources` would list."""

    def __init__(self) -> None:
        self.people: dict[PersonId, Person] = {}
        self.saved: dict[UUID, SpeakerMapping] = {}
        self.receipts: list[Receipt] = []
        self.events: list[tuple[EventType, tuple[Subject, ...], str]] = []
        self.transcripts: dict[ProjectId, list[TranscriptSpeakers]] = {
            PROJECT: [
                TranscriptSpeakers(
                    KICKOFF,
                    UUID(int=201),
                    (_label("Mira"), _label("Dana Ruiz"), _label("Speaker 1"), _label("Ana")),
                )
            ]
        }

    # PeopleStore
    def in_project(self, project_id: ProjectId) -> list[Person]:
        return [p for p in self.people.values() if p.project_id == project_id]

    def get(self, person_id: PersonId) -> Person | None:
        return self.people.get(person_id)

    def add(self, person: Person) -> None:
        self.people[person.id] = person

    def save(self, person: Person, *, expected_revision: int) -> bool:
        if self.people[person.id].revision != expected_revision:
            return False
        self.people[person.id] = person
        return True

    # SpeakerMappingStore
    def mappings(self, project_id: ProjectId) -> list[SpeakerMapping]:
        return list(self.saved.values())

    def save_mapping(
        self, project_id: ProjectId, mapping: SpeakerMapping, *, expected_revision: int
    ) -> bool:
        current = self.saved.get(mapping.source_id)
        if (current.revision if current else 0) != expected_revision:
            return False
        self.saved[mapping.source_id] = mapping
        return True

    # SpeakerLabelReader
    def labels(self, project_id: ProjectId) -> list[TranscriptSpeakers]:
        return self.transcripts.get(project_id, [])

    # ReceiptStore
    def find(self, actor_id: UserId, idempotency_key: str) -> Receipt | None:
        return next(
            (
                r
                for r in self.receipts
                if (r.actor_id, r.idempotency_key) == (actor_id, idempotency_key)
            ),
            None,
        )

    def add_receipt(self, receipt: Receipt) -> None:
        self.receipts.append(receipt)

    # AuditRecorder
    def record(
        self,
        *,
        project_id: ProjectId,
        actor: AuditActor,
        type: EventType,  # noqa: A002
        subjects: Sequence[Subject],
        summary: str,
        occurred_at: datetime,
    ) -> None:
        self.events.append((type, tuple(subjects), summary))


class _Mappings:
    def __init__(self, fakes: Fakes) -> None:
        self.mappings = fakes.mappings
        self.save = fakes.save_mapping


class _Receipts:
    def __init__(self, fakes: Fakes) -> None:
        self.find = fakes.find
        self.add = fakes.add_receipt


def _access(*roles: Role, project: ProjectId = PROJECT) -> ProjectAccess:
    return ProjectAccess(actor=EDITOR, project_id=project, roles=frozenset(roles))


def _assign(
    fakes: Fakes,
    *choices: tuple[str, SpeakerChoice],
    revision: int = 0,
    key: str = "key-0001",
    source: UUID = KICKOFF,
    access: ProjectAccess | None = None,
    now: datetime = NOW,
) -> TranscriptView:
    return assign_speakers(
        fakes,
        _Mappings(fakes),
        fakes.labels,
        _Receipts(fakes),
        fakes,
        access or _access(Role.EDITOR),
        AssignSpeakers(key, source, revision, tuple(choices)),
        now,
    )


def _status(view: TranscriptView) -> dict[str, tuple[str, PersonId | None]]:
    return {s.label.key: (s.status, s.person_id) for s in view.speakers}


@pytest.fixture
def fakes() -> Fakes:
    fakes = Fakes()
    record_extracted_people(fakes, PROJECT, UUID(int=1), [DANA], NOW)
    return fakes


def _dana(fakes: Fakes) -> Person:
    return next(p for p in fakes.people.values() if p.base_name == "Dana Ruiz")


def test_every_speaker_starts_unconfirmed_and_any_member_can_list_them(fakes: Fakes) -> None:
    [view] = list_speakers(fakes, _Mappings(fakes), fakes.labels, _access(Role.VIEWER))

    assert view.revision == 0
    assert {status for status, _ in _status(view).values()} == {"unconfirmed"}


def test_links_an_existing_person_creates_a_participant_and_marks_not_a_person(
    fakes: Fakes,
) -> None:
    dana = _dana(fakes)

    view = _assign(
        fakes,
        ("dana ruiz", LinkParticipant(dana.id, "Sponsor")),
        ("mira", NewParticipant("  Mira   Holt ", "Workshop lead")),
        ("speaker 1", NotAPerson()),
    )

    mira = next(p for p in fakes.people.values() if p.origin == "confirmed_speaker")
    assert (mira.entered_name, mira.name, mira.extracted) == ("Mira Holt", "Mira Holt", None)
    assert mira.meeting_role is not None
    assert mira.meeting_role.value == "Workshop lead"
    assert _dana(fakes).meeting_role is not None
    assert _dana(fakes).revision == dana.revision + 1
    assert view.revision == 1
    assert _status(view) == {
        "mira": ("linked", mira.id),
        "dana ruiz": ("linked", dana.id),
        "speaker 1": ("not_a_person", None),
        "ana": ("unconfirmed", None),
    }


def test_records_one_event_that_names_nobody(fakes: Fakes) -> None:
    _assign(fakes, ("mira", NewParticipant("Mira Holt", None)), ("speaker 1", NotAPerson()))

    [(event_type, subjects, summary)] = fakes.events
    assert event_type is EventType.SPEAKERS_CONFIRMED
    assert subjects[0] == Subject(SubjectKind.SOURCE, KICKOFF)
    assert [s.kind for s in subjects[1:]] == [SubjectKind.PERSON]
    assert summary == (
        "Confirmed who's who in a transcript: 1 speaker linked, 1 new participant, 1 not a person"
    )
    assert "Mira" not in summary


def test_two_labels_can_be_one_participant(fakes: Fakes) -> None:
    view = _assign(
        fakes,
        ("mira", NewParticipant("Mira Holt", None)),
        ("ana", NewParticipant("mira holt", None)),
    )

    assert len([p for p in fakes.people.values() if p.origin == "confirmed_speaker"]) == 1
    assert _status(view)["mira"] == _status(view)["ana"]


def test_a_label_left_out_goes_back_to_unconfirmed(fakes: Fakes) -> None:
    _assign(fakes, ("speaker 1", NotAPerson()), ("ana", NotAPerson()))

    view = _assign(fakes, ("ana", NotAPerson()), revision=1, key="key-0002")

    assert _status(view)["speaker 1"] == ("unconfirmed", None)
    assert view.revision == 2


def test_a_stale_revision_is_refused_with_the_current_one(fakes: Fakes) -> None:
    _assign(fakes, ("ana", NotAPerson()))

    with pytest.raises(SpeakersChangedError) as raised:
        _assign(fakes, ("ana", NotAPerson()), revision=0, key="key-0002")

    assert raised.value.details == {"current_revision": 1}


def test_saving_the_same_answer_keeps_the_revision_and_records_nothing(fakes: Fakes) -> None:
    _assign(fakes, ("ana", NotAPerson()))

    view = _assign(fakes, ("ana", NotAPerson()), revision=1, key="key-0002", now=LATER)

    assert view.revision == 1
    assert len(fakes.events) == 1
    [answer] = fakes.saved[KICKOFF].assignments
    assert answer.assigned_at == NOW


def test_a_retry_returns_the_same_result_and_a_reused_key_is_refused(fakes: Fakes) -> None:
    first = _assign(fakes, ("mira", NewParticipant("Mira Holt", "Sponsor")))

    again = _assign(fakes, ("mira", NewParticipant("Mira Holt", "Sponsor")))

    assert again == first
    assert len(fakes.people) == 2
    assert len(fakes.events) == 1
    with pytest.raises(IdempotencyKeyReusedError):
        _assign(fakes, ("mira", NotAPerson()), revision=1)


@pytest.mark.parametrize(
    ("choice", "field"),
    [
        (NewParticipant("   ", None), "speakers[0].name"),
        (NewParticipant("M" * 81, None), "speakers[0].name"),
        (NewParticipant("Mira Holt", "R" * 81), "speakers[0].meeting_role"),
        (LinkParticipant(PersonId(UUID(int=999)), None), "speakers[0].person_id"),
    ],
)
def test_invalid_answers_are_refused_next_to_their_field(
    fakes: Fakes, choice: SpeakerChoice, field: str
) -> None:
    with pytest.raises(InvalidInputError) as raised:
        _assign(fakes, ("mira", choice))

    assert raised.value.details["field"] == field
    assert fakes.saved == {}


def test_a_label_the_transcript_does_not_have_is_refused(fakes: Fakes) -> None:
    with pytest.raises(InvalidInputError):
        _assign(fakes, ("tomas", NotAPerson()))


def test_a_new_participant_may_not_take_a_known_person_s_name(fakes: Fakes) -> None:
    with pytest.raises(ParticipantExistsError) as raised:
        _assign(fakes, ("dana ruiz", NewParticipant("dana  ruiz", None)))

    assert raised.value.details["person_id"] == str(_dana(fakes).id)


def test_one_participant_cannot_get_two_meeting_roles_at_once(fakes: Fakes) -> None:
    dana = _dana(fakes)

    with pytest.raises(InvalidInputError):
        _assign(
            fakes,
            ("dana ruiz", LinkParticipant(dana.id, "Sponsor")),
            ("ana", LinkParticipant(dana.id, "Designer")),
        )


def test_saving_needs_an_editor_and_a_transcript_of_the_project(fakes: Fakes) -> None:
    with pytest.raises(PermissionDeniedError):
        _assign(fakes, ("ana", NotAPerson()), access=_access(Role.VIEWER, Role.APPROVER))
    with pytest.raises(NotFoundError):
        _assign(fakes, ("ana", NotAPerson()), access=_access())
    with pytest.raises(NotFoundError):
        _assign(fakes, ("ana", NotAPerson()), source=UUID(int=999))
    with pytest.raises(NotFoundError):
        _assign(fakes, ("ana", NotAPerson()), access=_access(Role.EDITOR, project=OTHER_PROJECT))


def test_a_new_version_of_the_transcript_keeps_its_answers(fakes: Fakes) -> None:
    _assign(fakes, ("mira", NewParticipant("Mira Holt", None)))
    [kickoff] = fakes.transcripts[PROJECT]
    fakes.transcripts[PROJECT] = [replace(kickoff, source_version_id=UUID(int=202))]

    [view] = list_speakers(fakes, _Mappings(fakes), fakes.labels, _access(Role.VIEWER))

    assert view.transcript.source_version_id == UUID(int=202)
    assert _status(view)["mira"][0] == "linked"


def test_a_later_transcript_links_a_known_participant_by_itself(fakes: Fakes) -> None:
    dana = _dana(fakes)
    _assign(
        fakes,
        ("mira", NewParticipant("Mira Holt", None)),
        ("ana", LinkParticipant(dana.id, None)),
        ("speaker 1", NewParticipant("Tomas Reed", None)),
    )
    labels = (_label("Mira Holt"), _label("Ana"), _label("Speaker 1"), _label("Dana Ruiz"))
    fakes.transcripts[PROJECT].append(TranscriptSpeakers(FOLLOW_UP, UUID(int=301), labels))

    views = list_speakers(fakes, _Mappings(fakes), fakes.labels, _access(Role.VIEWER))

    mira = next(p for p in fakes.people.values() if p.base_name == "Mira Holt")
    assert _status(views[1]) == {
        # By the name an editor gave.
        "mira holt": ("linked_automatically", mira.id),
        # By the label linked in the kickoff.
        "ana": ("linked_automatically", dana.id),
        # Generic labels are different people in each meeting.
        "speaker 1": ("unconfirmed", None),
        # Dana is confirmed now, through the kickoff's "ana".
        "dana ruiz": ("linked_automatically", dana.id),
    }


def test_the_agent_s_reading_alone_never_links_a_speaker(fakes: Fakes) -> None:
    [view] = list_speakers(fakes, _Mappings(fakes), fakes.labels, _access(Role.VIEWER))

    assert _status(view)["dana ruiz"] == ("unconfirmed", None)


def test_a_run_fills_in_a_confirmed_participant_without_overwriting_them(fakes: Fakes) -> None:
    _assign(fakes, ("mira", NewParticipant("Mira Holt", "Workshop lead")))
    mira = next(p for p in fakes.people.values() if p.origin == "confirmed_speaker")
    reading = replace(DANA, name="mira holt", role="Volunteer", said="Leads the workshop.")

    record_extracted_people(fakes, PROJECT, UUID(int=2), [reading], LATER)

    updated = fakes.people[mira.id]
    assert len(fakes.people) == 2
    assert updated.extracted == reading
    assert (updated.origin, updated.name, updated.entered_name) == (
        "confirmed_speaker",
        "Mira Holt",
        "Mira Holt",
    )
    assert updated.meeting_role == mira.meeting_role


def test_a_reading_of_a_confirmed_speaker_is_stored_on_them_and_renames_nobody(
    fakes: Fakes,
) -> None:
    _assign(fakes, ("mira", NewParticipant("Mira Holt", "Workshop lead")))
    mira = next(p for p in fakes.people.values() if p.origin == "confirmed_speaker")
    reading = replace(DANA, name="Mira", role="Volunteer", person_id=mira.id)

    record_extracted_people(fakes, PROJECT, UUID(int=3), [reading], LATER)

    updated = fakes.people[mira.id]
    assert len(fakes.people) == 2
    assert updated.extracted == reading
    assert (updated.name, updated.entered_name) == ("Mira Holt", "Mira Holt")
    assert updated.meeting_role == mira.meeting_role
