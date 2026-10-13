from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from scopesteps.audit.application.feed import (
    decode_cursor,
    encode_cursor,
    list_activity,
)
from scopesteps.audit.application.recording import record_event
from scopesteps.audit.client import AuditActor, EventType, Subject, SubjectKind
from scopesteps.audit.domain.event import (
    MAX_SUBJECTS,
    MAX_SUMMARY_CHARS,
    ActorKind,
    AuditEvent,
    FeedCursor,
    InvalidCursorError,
)
from scopesteps.audit.domain.ids import AuditEventId
from scopesteps.identity.client import Actor, ProjectAccess, Role, UserId
from scopesteps.kernel.errors import NotFoundError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

PROJECT = ProjectId(UUID("019a3a5e-0000-7000-8000-0000000000a1"))
OTHER_PROJECT = ProjectId(UUID("019a3a5e-0000-7000-8000-0000000000a2"))
DANA = Actor(user_id=UserId(UUID("019a3a5e-0000-7000-8000-0000000000b1")), display_name="Dana")
RUN = Subject(SubjectKind.RUN, UUID("019a3a5e-0000-7000-8000-0000000000c1"))
NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


class InMemoryEventStore:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def add(self, event: AuditEvent) -> None:
        self.events.append(event)

    def newest_first(
        self, project_id: ProjectId, *, after: FeedCursor | None, limit: int
    ) -> list[AuditEvent]:
        ordered = sorted(
            (event for event in self.events if event.project_id == project_id),
            key=lambda event: (event.occurred_at, event.id),
            reverse=True,
        )
        if after is not None:
            ordered = [e for e in ordered if (e.occurred_at, e.id) < (after.occurred_at, after.id)]
        return ordered[:limit]


def _record(
    store: InMemoryEventStore,
    *,
    summary: str = "Started a run on 2 source versions",
    project_id: ProjectId = PROJECT,
    actor: AuditActor | None = None,
    subjects: tuple[Subject, ...] = (RUN,),
    occurred_at: datetime = NOW,
) -> AuditEvent:
    return record_event(
        store,
        project_id=project_id,
        actor=actor or AuditActor.user(DANA),
        type=EventType.RUN_STARTED,
        subjects=subjects,
        summary=summary,
        occurred_at=occurred_at,
    )


def _access(*roles: Role, project_id: ProjectId = PROJECT) -> ProjectAccess:
    return ProjectAccess(actor=DANA, project_id=project_id, roles=frozenset(roles))


def test_a_recorded_event_names_the_project_actor_type_subjects_time_and_summary() -> None:
    store = InMemoryEventStore()

    event = _record(store)

    assert store.events == [event]
    assert (event.project_id, event.type, event.subjects) == (PROJECT, "run.started", (RUN,))
    assert event.actor == AuditActor(ActorKind.USER, DANA.user_id, "Dana")
    assert (event.summary, event.occurred_at) == ("Started a run on 2 source versions", NOW)


def test_the_agent_is_an_actor_without_a_user() -> None:
    event = _record(InMemoryEventStore(), actor=AuditActor.agent())

    assert event.actor == AuditActor(ActorKind.AGENT, None, None)


@pytest.mark.parametrize(
    ("kind", "user_id", "display_name"),
    [
        (ActorKind.USER, None, None),
        (ActorKind.AGENT, DANA.user_id, "Dana"),
        (ActorKind.USER, DANA.user_id, None),
        (ActorKind.USER, DANA.user_id, "Dana\nLee"),
    ],
)
def test_an_actor_is_a_named_user_or_the_agent(
    kind: ActorKind, user_id: UserId | None, display_name: str | None
) -> None:
    with pytest.raises(ValueError, match="actor"):
        AuditActor(kind, user_id, display_name)


@pytest.mark.parametrize(
    "summary",
    ["", "   ", "x" * (MAX_SUMMARY_CHARS + 1), "Students book rooms.\n\nNo recurring bookings."],
)
def test_a_summary_is_one_short_line(summary: str) -> None:
    store = InMemoryEventStore()

    with pytest.raises(ValueError, match="summary"):
        _record(store, summary=summary)

    assert store.events == []


@pytest.mark.parametrize("count", [0, MAX_SUBJECTS + 1])
def test_an_event_concerns_a_bounded_number_of_subjects(count: int) -> None:
    with pytest.raises(ValueError, match="subjects"):
        _record(InMemoryEventStore(), subjects=(RUN,) * count)


def test_an_event_time_is_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone"):
        _record(InMemoryEventStore(), occurred_at=datetime(2026, 10, 13, 9, 0))  # noqa: DTZ001


def test_the_feed_is_newest_first_with_the_id_breaking_ties() -> None:
    store = InMemoryEventStore()
    older = _record(store, occurred_at=NOW - timedelta(minutes=1))
    first_at_now = _record(store)
    second_at_now = _record(store)
    _record(store, project_id=OTHER_PROJECT)

    page = list_activity(store, _access(Role.VIEWER), limit=10, cursor=None)

    assert page.events == (second_at_now, first_at_now, older)
    assert page.next_cursor is None


def test_pages_follow_each_other_without_gaps_or_repeats() -> None:
    store = InMemoryEventStore()
    recorded = [_record(store) for _ in range(5)]
    access = _access(Role.VIEWER)

    first = list_activity(store, access, limit=2, cursor=None)
    second = list_activity(store, access, limit=2, cursor=first.next_cursor)
    third = list_activity(store, access, limit=2, cursor=second.next_cursor)

    assert [*first.events, *second.events, *third.events] == recorded[::-1]
    assert (len(first.events), len(second.events), len(third.events)) == (2, 2, 1)
    assert second.next_cursor is not None
    assert third.next_cursor is None


def test_a_page_that_ends_exactly_at_the_oldest_event_has_no_next_cursor() -> None:
    store = InMemoryEventStore()
    _record(store)
    _record(store)

    page = list_activity(store, _access(Role.VIEWER), limit=2, cursor=None)

    assert len(page.events) == 2
    assert page.next_cursor is None


def test_an_event_recorded_after_a_page_was_read_does_not_shift_the_next_page() -> None:
    store = InMemoryEventStore()
    oldest, middle, newest = (_record(store) for _ in range(3))
    access = _access(Role.VIEWER)
    first = list_activity(store, access, limit=2, cursor=None)

    _record(store)
    second = list_activity(store, access, limit=2, cursor=first.next_cursor)

    assert first.events == (newest, middle)
    assert second.events == (oldest,)


@pytest.mark.parametrize("role", list(Role))
def test_any_member_reads_the_log(role: Role) -> None:
    store = InMemoryEventStore()
    event = _record(store)

    page = list_activity(store, _access(role), limit=10, cursor=None)

    assert page.events == (event,)


def test_a_project_the_actor_has_no_role_in_is_not_found() -> None:
    store = InMemoryEventStore()
    _record(store)

    with pytest.raises(NotFoundError):
        list_activity(store, _access(), limit=10, cursor=None)


def test_a_cursor_round_trips() -> None:
    cursor = FeedCursor(NOW, AuditEventId(new_id()))

    assert decode_cursor(encode_cursor(cursor)) == cursor


@pytest.mark.parametrize(
    "cursor",
    [
        "not-a-cursor",
        "!!!",
        "MjAyNi0xMC0xM1QwOTowMDowMHxub3QtYS11dWlk",
        "MjAyNi0xMC0xM1QwOTowMDowMHwwMTlhM2E1ZS0wMDAwLTcwMDAtODAwMC0wMDAwMDAwMDAwYzE=",
    ],
    ids=["not-base64-of-a-pair", "not-base64", "bad-uuid", "naive-time"],
)
def test_a_cursor_the_feed_did_not_return_is_rejected(cursor: str) -> None:
    with pytest.raises(InvalidCursorError):
        list_activity(InMemoryEventStore(), _access(Role.VIEWER), limit=10, cursor=cursor)
