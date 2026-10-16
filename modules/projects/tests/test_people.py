"""People use cases against an in-memory store. All names are synthetic."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from scopesteps.audit.client import AuditActor, EventType, Subject, SubjectKind
from scopesteps.identity.client import Actor, ProjectAccess, Role, UserId
from scopesteps.kernel.errors import InvalidInputError, NotFoundError, PermissionDeniedError
from scopesteps.projects.application.people import (
    ConfirmRights,
    CorrectPerson,
    confirm_rights,
    correct_person,
    list_people,
    record_extracted_people,
)
from scopesteps.projects.application.receipts import IdempotencyKeyReusedError, Receipt
from scopesteps.projects.client import (
    MAX_PEOPLE_PER_RUN,
    ExtractedPerson,
    PersonEvidence,
    PersonId,
    ProjectId,
    name_key,
)
from scopesteps.projects.domain.person import (
    ConfirmedRights,
    Person,
    PersonChangedError,
    RightsStatedInSourceError,
)

PROJECT = ProjectId(UUID("019a3a5e-0000-7000-8000-0000000000a1"))
OTHER_PROJECT = ProjectId(UUID("019a3a5e-0000-7000-8000-0000000000a2"))
EDITOR = Actor(user_id=UserId(UUID("019a3a5e-0000-7000-8000-0000000000b1")), display_name="Edit")
RUN, LATER_RUN = UUID(int=1), UUID(int=2)
NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)
NAMED = PersonEvidence(UUID(int=11), UUID(int=12), "Dana Ruiz (Facilities Manager)")
CONFIRMS = PersonEvidence(UUID(int=11), UUID(int=13), "stays open until Dana confirms")

DANA = ExtractedPerson(
    name="Dana Ruiz",
    role="Facilities Manager",
    said="Wants a shorter maximum booking.",
    stated_rights="not_stated",
    evidence=(NAMED,),
)
SAM = replace(DANA, name="Sam Okafor", role="Student Union representative", said="")
DANA_DECIDES = replace(DANA, stated_rights="decides", rights_evidence=(CONFIRMS,))


@dataclass(frozen=True)
class Recorded:
    project_id: ProjectId
    actor: AuditActor
    type: EventType
    subjects: tuple[Subject, ...]
    summary: str
    occurred_at: datetime


class InMemoryReceipts:
    def __init__(self) -> None:
        self.receipts: list[Receipt] = []

    def find(self, actor_id: UserId, idempotency_key: str) -> Receipt | None:
        return next(
            (
                receipt
                for receipt in self.receipts
                if (receipt.actor_id, receipt.idempotency_key) == (actor_id, idempotency_key)
            ),
            None,
        )

    def add(self, receipt: Receipt) -> None:
        self.receipts.append(receipt)


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[Recorded] = []

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
        self.events.append(Recorded(project_id, actor, type, tuple(subjects), summary, occurred_at))


class InMemoryPeopleStore:
    """The people, plus the receipts and audit events the commands write beside them."""

    def __init__(self) -> None:
        self.people: dict[PersonId, Person] = {}
        self.receipts = InMemoryReceipts()
        self.audit = RecordingAudit()

    def in_project(self, project_id: ProjectId) -> list[Person]:
        return [person for person in self.people.values() if person.project_id == project_id]

    def get(self, person_id: PersonId) -> Person | None:
        return self.people.get(person_id)

    def add(self, person: Person) -> None:
        self.people[person.id] = person

    def save(self, person: Person, *, expected_revision: int) -> bool:
        if self.people[person.id].revision != expected_revision:
            return False
        self.people[person.id] = person
        return True

    @property
    def events(self) -> list[Recorded]:
        return self.audit.events


def _access(*roles: Role, project: ProjectId = PROJECT) -> ProjectAccess:
    return ProjectAccess(actor=EDITOR, project_id=project, roles=frozenset(roles))


@pytest.fixture
def store() -> InMemoryPeopleStore:
    people = InMemoryPeopleStore()
    record_extracted_people(people, PROJECT, RUN, [DANA, SAM], NOW)
    return people


def _named(store: InMemoryPeopleStore, name: str) -> Person:
    return next(person for person in store.in_project(PROJECT) if person.base_name == name)


def _correct(
    store: InMemoryPeopleStore,
    person: Person,
    *,
    name: str | None = None,
    role: str | None = None,
    key: str = "correct-key-0001",
    revision: int | None = None,
    access: ProjectAccess | None = None,
    now: datetime = NOW,
) -> Person:
    command = CorrectPerson(key, person.id, revision or person.revision, name, role)
    return correct_person(
        store, store.receipts, store.audit, access or _access(Role.EDITOR), command, now
    )


def _confirm(
    store: InMemoryPeopleStore,
    person: Person,
    rights: ConfirmedRights = "decides",
    *,
    key: str = "rights-key-0001",
    access: ProjectAccess | None = None,
) -> Person:
    command = ConfirmRights(key, person.id, person.revision, rights)
    return confirm_rights(
        store, store.receipts, store.audit, access or _access(Role.EDITOR), command, LATER
    )


def test_a_run_adds_the_people_it_named_without_committing(store: InMemoryPeopleStore) -> None:
    people = list_people(store, _access(Role.VIEWER))

    assert [(p.name, p.role, p.revision, p.run_id) for p in people] == [
        ("Dana Ruiz", "Facilities Manager", 1, RUN),
        ("Sam Okafor", "Student Union representative", 1, RUN),
    ]
    assert all(p.correction is None and p.confirmed_rights is None for p in people)
    assert store.events == [], "storing a run's people is the run's action, not a correction"


def test_a_correction_is_stored_beside_the_extraction_with_who_and_when(
    store: InMemoryPeopleStore,
) -> None:
    corrected = _correct(
        store, _named(store, "Dana Ruiz"), name=" Dana  Ruiz-Lopez ", role="Sponsor"
    )

    assert (corrected.name, corrected.role, corrected.revision) == ("Dana Ruiz-Lopez", "Sponsor", 2)
    assert corrected.extracted == DANA, "the agent's reading is untouched"
    assert corrected.correction is not None
    assert (corrected.correction.corrected_by, corrected.correction.corrected_at) == (
        EDITOR.user_id,
        NOW,
    )
    assert store.get(corrected.id) == corrected
    assert store.events == [
        Recorded(
            PROJECT,
            AuditActor.user(EDITOR),
            EventType.PERSON_CORRECTED,
            (Subject(SubjectKind.PERSON, corrected.id),),
            "Corrected a person's name and role",
            NOW,
        )
    ]
    assert "Dana" not in store.events[0].summary, "the log names no person"


def test_a_value_equal_to_the_agents_is_no_correction(store: InMemoryPeopleStore) -> None:
    dana = _correct(store, _named(store, "Dana Ruiz"), name="Dana R.", role="Facilities Manager")

    reverted = _correct(store, dana, name="Dana Ruiz", key="correct-key-0002", now=LATER)

    assert dana.correction is not None
    assert (dana.correction.name, dana.correction.role) == ("Dana R.", None)
    assert reverted.correction is not None
    assert (reverted.correction.name, reverted.correction.role) == (None, None)
    assert (reverted.name, reverted.correction.corrected_at) == ("Dana Ruiz", LATER)


def test_a_role_can_be_corrected_to_none(store: InMemoryPeopleStore) -> None:
    assert _correct(store, _named(store, "Dana Ruiz"), role="").role == ""


@pytest.mark.parametrize(("name", "role"), [("   ", None), ("x" * 81, None), (None, "x" * 81)])
def test_a_correction_must_fit_the_stored_lengths(
    store: InMemoryPeopleStore, name: str | None, role: str | None
) -> None:
    with pytest.raises(InvalidInputError):
        _correct(store, _named(store, "Dana Ruiz"), name=name, role=role)


def test_a_stale_revision_changes_nothing(store: InMemoryPeopleStore) -> None:
    dana = _correct(store, _named(store, "Dana Ruiz"), name="Dana R.")

    with pytest.raises(PersonChangedError) as raised:
        _correct(store, dana, name="D. Ruiz", key="correct-key-0002", revision=1)

    assert raised.value.details == {"current_revision": 2}
    assert _named(store, "Dana Ruiz").name == "Dana R."


def test_a_retry_with_the_same_key_does_not_act_twice(store: InMemoryPeopleStore) -> None:
    dana = _named(store, "Dana Ruiz")
    first = _correct(store, dana, name="Dana R.")

    retried = _correct(store, dana, name="Dana R.", now=LATER)

    assert retried == first
    assert retried.revision == 2, "the stale revision of the retry is not an error"
    assert len(store.events) == 1
    assert len(store.receipts.receipts) == 1


def test_a_correction_that_changes_nothing_shown_records_nothing(
    store: InMemoryPeopleStore,
) -> None:
    dana = _named(store, "Dana Ruiz")

    unchanged = _correct(store, dana, name="Dana Ruiz", role="Facilities Manager")

    assert unchanged == dana, "the revision does not move"
    assert store.events == []
    assert len(store.receipts.receipts) == 1, "a retry still gets the same answer"


def test_a_key_reused_for_another_request_is_refused(store: InMemoryPeopleStore) -> None:
    dana = _correct(store, _named(store, "Dana Ruiz"), name="Dana R.")

    with pytest.raises(IdempotencyKeyReusedError):
        _correct(store, dana, name="Someone Else")
    with pytest.raises(IdempotencyKeyReusedError):
        _confirm(store, dana, "unknown", key="correct-key-0001")


@pytest.mark.parametrize("rights", ["decides", "advises", "unknown"])
def test_rights_no_source_states_can_be_confirmed_with_who_and_when(
    store: InMemoryPeopleStore, rights: ConfirmedRights
) -> None:
    confirmed = _confirm(store, _named(store, "Sam Okafor"), rights)

    assert confirmed.confirmed_rights is not None
    assert (
        confirmed.confirmed_rights.rights,
        confirmed.confirmed_rights.confirmed_by,
        confirmed.confirmed_rights.confirmed_at,
    ) == (rights, EDITOR.user_id, LATER)
    assert (confirmed.revision, confirmed.stated_rights) == (2, "not_stated")
    (event,) = store.events
    assert (event.type, event.subjects, event.occurred_at) == (
        EventType.PERSON_RIGHTS_CONFIRMED,
        (Subject(SubjectKind.PERSON, confirmed.id),),
        LATER,
    )
    assert "Sam" not in event.summary


def test_confirming_the_rights_already_confirmed_records_nothing(
    store: InMemoryPeopleStore,
) -> None:
    sam = _confirm(store, _named(store, "Sam Okafor"), "advises")

    again = _confirm(store, sam, "advises", key="rights-key-0002")

    assert again == sam
    assert len(store.events) == 1


def test_rights_a_source_states_cannot_be_confirmed_by_hand() -> None:
    store = InMemoryPeopleStore()
    record_extracted_people(store, PROJECT, RUN, [DANA_DECIDES], NOW)

    with pytest.raises(RightsStatedInSourceError):
        _confirm(store, _named(store, "Dana Ruiz"), "advises")

    assert _named(store, "Dana Ruiz").confirmed_rights is None
    assert store.events == []
    assert store.receipts.receipts == [], "a refused command leaves no receipt"


def test_confirming_rights_checks_the_revision(store: InMemoryPeopleStore) -> None:
    sam = _named(store, "Sam Okafor")
    _correct(store, sam, role="Students")

    with pytest.raises(PersonChangedError):
        _confirm(store, sam)


@pytest.mark.parametrize("roles", [(Role.VIEWER,), (Role.APPROVER,), (Role.VIEWER, Role.APPROVER)])
def test_members_without_the_editor_role_can_read_but_not_change(
    store: InMemoryPeopleStore, roles: tuple[Role, ...]
) -> None:
    dana = _named(store, "Dana Ruiz")

    assert len(list_people(store, _access(*roles))) == 2
    with pytest.raises(PermissionDeniedError):
        _correct(store, dana, name="Dana R.", access=_access(*roles))
    with pytest.raises(PermissionDeniedError):
        _confirm(store, dana, access=_access(*roles))
    assert store.get(dana.id) == dana
    assert store.events == []


def test_people_are_hidden_from_non_members_and_other_projects(store: InMemoryPeopleStore) -> None:
    dana = _named(store, "Dana Ruiz")

    with pytest.raises(NotFoundError, match="Project not found"):
        list_people(store, _access())
    with pytest.raises(NotFoundError, match="Project not found"):
        _correct(store, dana, name="Dana R.", access=_access())
    with pytest.raises(NotFoundError, match="Person not found"):
        _correct(store, dana, name="Dana R.", access=_access(Role.EDITOR, project=OTHER_PROJECT))
    assert list_people(store, _access(Role.EDITOR, project=OTHER_PROJECT)) == []


def test_a_later_run_updates_the_reading_and_keeps_what_people_changed(
    store: InMemoryPeopleStore,
) -> None:
    dana = _correct(store, _named(store, "Dana Ruiz"), role="Sponsor")
    sam = _confirm(store, _named(store, "Sam Okafor"), "advises")
    reread = replace(DANA, name="DANA  ruiz", role="Facilities lead", said="Chairs the meeting.")

    record_extracted_people(store, PROJECT, LATER_RUN, [reread, SAM], LATER)

    after = {person.id: person for person in store.in_project(PROJECT)}
    assert len(after) == 2, "matched by name, not added again"
    assert after[dana.id].extracted == reread
    assert (after[dana.id].role, after[dana.id].correction) == ("Sponsor", dana.correction)
    assert (after[dana.id].revision, after[dana.id].run_id) == (dana.revision + 1, LATER_RUN)
    assert after[sam.id].confirmed_rights == sam.confirmed_rights
    assert (after[sam.id].revision, after[sam.id].run_id, after[sam.id].extracted_at) == (
        sam.revision,
        LATER_RUN,
        LATER,
    ), "an unchanged reading does not invalidate an open edit form"


def test_a_later_run_matches_a_person_by_their_corrected_name(store: InMemoryPeopleStore) -> None:
    misread = replace(DANA, name="Dana Ruis")
    store.people.clear()
    record_extracted_people(store, PROJECT, RUN, [misread], NOW)
    fixed = _correct(store, _named(store, "Dana Ruis"), name="Dana Ruiz")

    record_extracted_people(store, PROJECT, LATER_RUN, [DANA], LATER)

    (person,) = store.in_project(PROJECT)
    assert (person.id, person.base_name, person.name) == (fixed.id, "Dana Ruiz", "Dana Ruiz")
    assert person.correction == fixed.correction


def test_a_later_run_that_names_fewer_people_removes_nobody(store: InMemoryPeopleStore) -> None:
    record_extracted_people(store, PROJECT, LATER_RUN, [SAM], LATER)

    assert [(p.name, p.run_id) for p in store.in_project(PROJECT)] == [
        ("Dana Ruiz", RUN),
        ("Sam Okafor", LATER_RUN),
    ]


def test_people_are_matched_inside_their_own_project_only(store: InMemoryPeopleStore) -> None:
    record_extracted_people(store, OTHER_PROJECT, LATER_RUN, [DANA], LATER)

    assert len(store.in_project(PROJECT)) == 2
    assert [p.run_id for p in store.in_project(OTHER_PROJECT)] == [LATER_RUN]


def test_a_name_repeated_in_one_run_is_stored_once() -> None:
    store = InMemoryPeopleStore()

    record_extracted_people(store, PROJECT, RUN, [DANA, replace(DANA, name="dana ruiz")], NOW)

    assert [p.base_name for p in store.in_project(PROJECT)] == ["Dana Ruiz"]


@pytest.mark.parametrize(
    "people",
    [
        [replace(DANA, evidence=())],
        [replace(DANA, name=" ")],
        [replace(DANA, stated_rights="decides")],
        [replace(DANA, rights_evidence=(CONFIRMS,))],
        [replace(DANA, said="x" * 241)],
        [replace(DANA, evidence=(replace(NAMED, quote="x" * 301),))],
        [replace(DANA, name=f"Person {n}") for n in range(MAX_PEOPLE_PER_RUN + 1)],
    ],
)
def test_people_that_break_the_rules_are_refused_and_nothing_is_stored(
    people: list[ExtractedPerson],
) -> None:
    store = InMemoryPeopleStore()

    with pytest.raises(InvalidInputError):
        record_extracted_people(store, PROJECT, RUN, [SAM, *people], NOW)

    assert store.people == {}


def test_names_match_whatever_their_case_spacing_or_unicode_form() -> None:
    no_break_space, combining_diaeresis = chr(0xA0), chr(0x308)

    assert name_key(f"  DANA{no_break_space} Ruiz ") == name_key("dana ruiz") == "dana ruiz"
    assert name_key(f"Zoe{combining_diaeresis}") == name_key(f"Zo{chr(0xEB)}")
