"""The project activity feed and the audit events behind it, through the API and the database."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID
from scopesteps.audit.client import AuditActor, EventType, Subject, SubjectKind, audit_recorder
from scopesteps.audit.infrastructure.orm import AuditEventImmutableError, AuditEventRecord
from scopesteps.identity.client import Actor, Role
from scopesteps.identity.domain.user import Membership
from scopesteps.identity.infrastructure.orm import MembershipRecord
from scopesteps.identity.infrastructure.repository import SqlUserRepository
from scopesteps.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    utc_now,
)
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId
from scopesteps.projects.domain.project import Project
from scopesteps.projects.infrastructure.repository import SqlProjectRepository
from scopesteps.sources.http import router as sources_router
from scopesteps.sources.infrastructure.orm import SourceVersionRecord
from scopesteps.sources.infrastructure.repository import SqlSourceRepository

ClientFactory = Callable[..., TestClient]

BRIEF = b"# Room booking\n\nStudents book study rooms.\n\nNo recurring bookings in release one."
TRANSCRIPT = b"**Dana:** Keep it to single slots.\n\n**Lee:** Agreed."
REVIEWER = Actor(user_id=LOCAL_REVIEWER_ID, display_name="Local Reviewer")
RUN = Subject(SubjectKind.RUN, UUID("019a3a5e-0000-7000-8000-0000000000c1"))


@contextmanager
def _session(database_url: str) -> Generator[Session]:
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        yield session
    engine.dispose()


def _upload(client: TestClient, key: str = "upload-key-0001", brief: bytes = BRIEF) -> Response:
    return client.post(
        f"/api/v1/projects/{DEMO_PROJECT_ID}/sources",
        files={"brief": ("brief.md", brief), "transcript": ("transcript.txt", TRANSCRIPT)},
        headers={"Idempotency-Key": key},
    )


def _feed(client: TestClient, project_id: ProjectId = DEMO_PROJECT_ID, **params: Any) -> Response:
    return client.get(f"/api/v1/projects/{project_id}/activity", params=params)


def _record(
    database_url: str,
    count: int,
    *,
    project_id: ProjectId = DEMO_PROJECT_ID,
    occurred_at: datetime | None = None,
) -> None:
    with _session(database_url) as session:
        recorder = audit_recorder(session)
        at = occurred_at or utc_now()
        for number in range(1, count + 1):
            recorder.record(
                project_id=project_id,
                actor=AuditActor.user(REVIEWER),
                type=EventType.RUN_STARTED,
                subjects=(RUN,),
                summary=f"Started run {number}",
                occurred_at=at,
            )
        session.commit()


def _add_project(database_url: str, *roles: Role) -> ProjectId:
    project_id = ProjectId(new_id())
    with _session(database_url) as session:
        SqlProjectRepository(session).add(
            Project(id=project_id, name="Makerspace Tool Library", created_at=utc_now())
        )
        session.flush()
        for role in roles:
            SqlUserRepository(session).add_membership(
                Membership(
                    user_id=LOCAL_REVIEWER_ID,
                    project_id=project_id,
                    role=role,
                    granted_at=utc_now(),
                )
            )
        session.commit()
    return project_id


def _stored(database_url: str, record: type[AuditEventRecord | SourceVersionRecord]) -> int:
    with _session(database_url) as session:
        return session.scalar(select(func.count()).select_from(record)) or 0


def test_an_upload_appears_in_the_feed_with_who_what_and_when(client: TestClient) -> None:
    brief, transcript = _upload(client).json()["source_versions"]

    response = _feed(client)

    assert response.status_code == 200
    body = response.json()
    assert body["next_cursor"] is None
    newest, oldest = body["events"]
    assert oldest == {
        "id": oldest["id"],
        "project_id": str(DEMO_PROJECT_ID),
        "type": "source.added",
        "actor": {
            "kind": "user",
            "user_id": str(LOCAL_REVIEWER_ID),
            "display_name": "Local Reviewer",
        },
        "subjects": [
            {"kind": "source", "id": brief["source_id"]},
            {"kind": "source_version", "id": brief["id"]},
        ],
        "summary": "Added the brief brief.md (version 1)",
        "occurred_at": oldest["occurred_at"],
    }
    assert newest["summary"] == "Added the transcript transcript.txt (version 1)"
    assert newest["subjects"][1]["id"] == transcript["id"]
    assert datetime.fromisoformat(oldest["occurred_at"]).utcoffset() == timedelta(0)


def test_only_uploads_that_create_a_version_are_recorded(client: TestClient) -> None:
    _upload(client)

    _upload(client)
    _upload(client, key="upload-key-0002")
    _upload(client, key="upload-key-0003", brief=b"A revised brief.")

    assert [event["summary"] for event in _feed(client).json()["events"]] == [
        "Added the brief brief.md (version 1)",
        "Added the transcript transcript.txt (version 1)",
        "Added the brief brief.md (version 1)",
    ]


def test_events_hold_no_document_text(client: TestClient, seeded_database_url: str) -> None:
    _upload(client)

    with _session(seeded_database_url) as session:
        stored = [
            f"{record.summary} {record.subjects} {record.actor_name}"
            for record in session.scalars(select(AuditEventRecord))
        ]

    assert len(stored) == 2
    assert not any("Students" in row or "single slots" in row for row in stored)


def test_an_action_that_fails_after_recording_leaves_no_event(
    client: TestClient, seeded_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailsLast(SqlSourceRepository):
        def add_receipt(self, receipt: object) -> None:
            raise RuntimeError("the action failed after its events were recorded")

    monkeypatch.setattr(sources_router, "SqlSourceRepository", FailsLast)

    with pytest.raises(RuntimeError, match="after its events were recorded"):
        _upload(client)

    assert _stored(seeded_database_url, AuditEventRecord) == 0
    assert _stored(seeded_database_url, SourceVersionRecord) == 0


def test_an_event_is_committed_or_rolled_back_with_the_callers_transaction(
    seeded_database_url: str,
) -> None:
    with _session(seeded_database_url) as session:
        recorder = audit_recorder(session)
        for summary, keep in (("Started run 1", False), ("Started run 2", True)):
            recorder.record(
                project_id=DEMO_PROJECT_ID,
                actor=AuditActor.agent(),
                type=EventType.RUN_STARTED,
                subjects=(RUN,),
                summary=summary,
                occurred_at=utc_now(),
            )
            session.flush()
            session.commit() if keep else session.rollback()

        summaries = list(session.scalars(select(AuditEventRecord.summary)))

    assert summaries == ["Started run 2"]


def test_the_feed_is_newest_first_and_same_time_events_keep_a_stable_order(
    client: TestClient, seeded_database_url: str
) -> None:
    now = utc_now()
    _record(seeded_database_url, 3, occurred_at=now - timedelta(hours=1))
    _record(seeded_database_url, 2, occurred_at=now)

    first = _feed(client).json()["events"]
    second = _feed(client).json()["events"]

    assert [event["summary"] for event in first] == [
        "Started run 2",
        "Started run 1",
        "Started run 3",
        "Started run 2",
        "Started run 1",
    ]
    assert first == second


def test_pages_cover_the_log_once_in_order(client: TestClient, seeded_database_url: str) -> None:
    _record(seeded_database_url, 5)
    everything = _feed(client).json()["events"]

    pages: list[list[dict[str, Any]]] = []
    cursor: str | None = None
    for _ in range(3):
        params: dict[str, Any] = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        body = _feed(client, **params).json()
        pages.append(body["events"])
        cursor = body["next_cursor"]

    assert [len(page) for page in pages] == [2, 2, 1]
    assert [event for page in pages for event in page] == everything
    assert cursor is None


def test_the_page_size_defaults_to_50_and_is_capped(
    client: TestClient, seeded_database_url: str
) -> None:
    _record(seeded_database_url, 51)

    default = _feed(client).json()

    assert len(default["events"]) == 50
    assert default["next_cursor"] is not None
    assert len(_feed(client, limit=100).json()["events"]) == 51
    assert _feed(client, limit=101).status_code == 422
    assert _feed(client, limit=0).status_code == 422


def test_a_cursor_the_feed_did_not_return_is_a_422(client: TestClient) -> None:
    response = _feed(client, cursor="not-a-cursor")

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_CURSOR"


def test_the_feed_runs_the_same_queries_for_any_number_of_events(
    client: TestClient, seeded_database_url: str
) -> None:
    statements: list[str] = []
    engine = client.app.state.engine  # type: ignore[attr-defined]

    def count(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    _record(seeded_database_url, 2)
    _feed(client)
    for_two_events = len(statements)
    _record(seeded_database_url, 40)
    statements.clear()

    events = _feed(client).json()["events"]

    event.remove(engine, "before_cursor_execute", count)
    assert len(events) == 42
    assert len(statements) == for_two_events
    assert sum("audit_events" in statement for statement in statements) == 1


@pytest.mark.parametrize("role", list(Role))
def test_a_member_with_any_role_reads_the_same_log(
    client: TestClient, seeded_database_url: str, role: Role
) -> None:
    _record(seeded_database_url, 2)
    as_editor = _feed(client).json()
    with _session(seeded_database_url) as session:
        session.execute(delete(MembershipRecord))
        SqlUserRepository(session).add_membership(
            Membership(
                user_id=LOCAL_REVIEWER_ID,
                project_id=DEMO_PROJECT_ID,
                role=role,
                granted_at=utc_now(),
            )
        )
        session.commit()

    response = _feed(client)

    assert response.status_code == 200
    assert response.json() == as_editor


def test_a_project_the_actor_is_not_a_member_of_looks_like_a_missing_one(
    client: TestClient, seeded_database_url: str
) -> None:
    foreign = _add_project(seeded_database_url)
    _record(seeded_database_url, 1, project_id=foreign)

    not_a_member = _feed(client, foreign)
    missing = _feed(client, ProjectId(new_id()))

    assert (not_a_member.status_code, missing.status_code) == (404, 404)
    assert not_a_member.json()["code"] == missing.json()["code"] == "NOT_FOUND"
    assert not_a_member.json()["message"] == missing.json()["message"]


def test_the_feed_shows_only_its_own_project(client: TestClient, seeded_database_url: str) -> None:
    other = _add_project(seeded_database_url, Role.VIEWER)
    _record(seeded_database_url, 2, project_id=other)
    _upload(client)

    demo = _feed(client).json()["events"]
    others = _feed(client, other).json()["events"]

    assert {event["type"] for event in demo} == {"source.added"}
    assert [event["project_id"] for event in others] == [str(other)] * 2


def test_the_feed_requires_a_loopback_actor(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    remote = make_client(seeded_database_url, client=("203.0.113.7", 50000))

    assert _feed(remote).status_code == 403


def test_the_api_has_no_route_that_changes_or_removes_an_event(client: TestClient) -> None:
    _upload(client)
    event_id = _feed(client).json()["events"][0]["id"]
    url = f"/api/v1/projects/{DEMO_PROJECT_ID}/activity"

    statuses = {
        client.request(method, target).status_code
        for method in ("POST", "PUT", "PATCH", "DELETE")
        for target in (url, f"{url}/{event_id}")
    }

    assert statuses <= {404, 405}
    assert len(_feed(client).json()["events"]) == 2


def test_a_stored_event_cannot_be_updated_or_deleted_through_the_orm(
    seeded_database_url: str,
) -> None:
    _record(seeded_database_url, 1)

    with _session(seeded_database_url) as session:
        record = session.scalars(select(AuditEventRecord)).one()
        record.summary = "Rewritten"
        with pytest.raises(AuditEventImmutableError):
            session.flush()
        session.rollback()
        session.delete(session.scalars(select(AuditEventRecord)).one())
        with pytest.raises(AuditEventImmutableError):
            session.flush()
        session.rollback()

        assert session.scalars(select(AuditEventRecord.summary)).all() == ["Started run 1"]


def test_the_database_refuses_an_actor_that_does_not_match_its_kind(
    seeded_database_url: str,
) -> None:
    _record(seeded_database_url, 1)

    with _session(seeded_database_url) as session, pytest.raises(IntegrityError):
        session.execute(
            update(AuditEventRecord)
            .values(actor_kind="agent")
            .execution_options(synchronize_session=False)
        )
