from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Engine, event, func, select
from sqlalchemy.orm import Session

from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID
from scopesteps.backlog.infrastructure.orm import VersionRecord
from scopesteps.identity.application.users import grant_project_roles
from scopesteps.identity.client import Role
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
from scopesteps.projects.http.router import resolve_project_reader
from scopesteps.projects.infrastructure.orm import ProjectRecord
from scopesteps.projects.infrastructure.repository import SqlProjectRepository

ClientFactory = Callable[..., TestClient]
Json = dict[str, Any]

PROJECTS_URL = "/api/v1/projects"
DEMO_URL = f"{PROJECTS_URL}/{DEMO_PROJECT_ID}"
MEMBER_ROLES = [Role.VIEWER, Role.EDITOR, Role.APPROVER]


@contextmanager
def _session(database_url: str) -> Generator[Session]:
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        yield session
        session.commit()
    engine.dispose()


def _add_project(database_url: str, *roles: Role, name: str = "Makerspace Tool Library") -> str:
    """Another project in which the local reviewer holds exactly `roles`."""
    project_id = ProjectId(new_id())
    with _session(database_url) as session:
        SqlProjectRepository(session).add(Project(id=project_id, name=name, created_at=utc_now()))
        grant_project_roles(
            SqlUserRepository(session), LOCAL_REVIEWER_ID, project_id, roles, utc_now()
        )
    return f"{PROJECTS_URL}/{project_id}"


def _add_versions(database_url: str, project_url: str, *states: str) -> list[str]:
    """Backlog versions in the given states, created one minute apart in the order given."""
    project_id = ProjectId(UUID(project_url.rsplit("/", 1)[1]))
    start = utc_now()
    ids = [new_id() for _ in states]
    with _session(database_url) as session:
        session.add_all(
            VersionRecord(
                id=version_id,
                project_id=project_id,
                base_version_id=None,
                revision=1,
                state=state,
                content_hash="0" * 64,
                schema_version="backlog-version.v1",
                run_id=None,
                source_version_ids=[],
                decisions=[],
                out_of_scope=[],
                created_by=LOCAL_REVIEWER_ID,
                created_at=start + timedelta(minutes=position),
            )
            for position, (version_id, state) in enumerate(zip(ids, states, strict=True))
        )
    return [str(version_id) for version_id in ids]


def _count(database_url: str, record: type[ProjectRecord] | type[MembershipRecord]) -> int:
    with _session(database_url) as session:
        return session.scalar(select(func.count()).select_from(record)) or 0


def _create(client: TestClient, name: str, key: str = "create-key-0001") -> Response:
    return client.post(PROJECTS_URL, json={"name": name}, headers={"Idempotency-Key": key})


def _rename(
    client: TestClient,
    url: str,
    name: str,
    expected_revision: int = 1,
    key: str = "rename-key-0001",
) -> Response:
    return client.patch(
        url,
        json={"name": name, "expected_revision": expected_revision},
        headers={"Idempotency-Key": key},
    )


def _listed(client: TestClient) -> list[Json]:
    response = client.get(PROJECTS_URL)
    assert response.status_code == 200
    projects: list[Json] = response.json()["projects"]
    return projects


@contextmanager
def _counting_queries(client: TestClient) -> Generator[list[str]]:
    engine: Engine = cast(FastAPI, client.app).state.engine
    statements: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_the_list_shows_the_seeded_project_with_the_reviewers_roles(client: TestClient) -> None:
    projects = _listed(client)

    assert len(projects) == 1
    project = projects[0]
    assert project["id"] == str(DEMO_PROJECT_ID)
    assert project["name"] == "Campus Room Booking"
    assert project["roles"] == ["editor", "approver"]
    assert project["revision"] == 1
    assert project["status"] == {
        "state": "no_baseline",
        "baseline_version": None,
        "baseline_version_id": None,
        "open_version_id": None,
    }
    assert "limits" not in project


@pytest.mark.parametrize("role", MEMBER_ROLES)
def test_the_list_reports_the_actors_role_in_each_project(
    seeded_database_url: str, make_client: ClientFactory, role: Role
) -> None:
    url = _add_project(seeded_database_url, role, name="Library Kiosk Refresh")

    projects = _listed(make_client(seeded_database_url))

    assert [(p["name"], p["roles"]) for p in projects] == [
        ("Campus Room Booking", ["editor", "approver"]),
        ("Library Kiosk Refresh", [role.value]),
    ]
    assert url.endswith(projects[1]["id"])


def test_the_list_leaves_out_projects_the_actor_is_not_a_member_of(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    _add_project(seeded_database_url)

    projects = _listed(make_client(seeded_database_url))

    assert [p["id"] for p in projects] == [str(DEMO_PROJECT_ID)]


def test_each_status_is_derived_from_the_projects_stored_versions(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    drafting = _add_project(seeded_database_url, Role.VIEWER, name="Drafting")
    reviewing = _add_project(seeded_database_url, Role.VIEWER, name="Evaluating a candidate")
    baselined = _add_project(seeded_database_url, Role.VIEWER, name="Fixed baseline")
    changing = _add_project(seeded_database_url, Role.VIEWER, name="Going through a change")
    (draft,) = _add_versions(seeded_database_url, drafting, "draft")
    candidate, _ = _add_versions(seeded_database_url, reviewing, "in_review", "rejected")
    _, first = _add_versions(seeded_database_url, baselined, "draft", "approved")
    _, second, change = _add_versions(
        seeded_database_url, changing, "approved", "approved", "draft"
    )

    statuses = [p["status"] for p in _listed(make_client(seeded_database_url))]

    assert statuses == [
        {
            "state": "no_baseline",
            "baseline_version": None,
            "baseline_version_id": None,
            "open_version_id": None,
        },
        {
            "state": "draft_in_progress",
            "baseline_version": None,
            "baseline_version_id": None,
            "open_version_id": draft,
        },
        {
            "state": "candidate_in_review",
            "baseline_version": None,
            "baseline_version_id": None,
            "open_version_id": candidate,
        },
        {
            "state": "baseline",
            "baseline_version": 1,
            "baseline_version_id": first,
            "open_version_id": None,
        },
        {
            "state": "draft_in_progress",
            "baseline_version": 2,
            "baseline_version_id": second,
            "open_version_id": change,
        },
    ]


def test_listing_more_projects_does_not_run_more_queries(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    client = make_client(seeded_database_url)
    with _counting_queries(client) as one_project:
        _listed(client)
    for number in range(4):
        url = _add_project(seeded_database_url, Role.EDITOR, name=f"Synthetic project {number}")
        _add_versions(seeded_database_url, url, "draft", "draft")

    with _counting_queries(client) as five_projects:
        projects = _listed(client)

    assert len(projects) == 5
    assert len(five_projects) == len(one_project)


def test_creating_a_project_makes_the_creator_its_editor_and_approver(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    client = make_client(seeded_database_url)

    response = _create(client, "  Makerspace Tool  Library ")

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Makerspace Tool Library"
    assert created["roles"] == ["editor", "approver"]
    assert created["revision"] == 1
    assert created["status"]["state"] == "no_baseline"
    assert created["limits"]["project_name_max_chars"] == 80
    assert client.get(f"{PROJECTS_URL}/{created['id']}").json() == created
    assert [p["name"] for p in _listed(client)] == [
        "Campus Room Booking",
        "Makerspace Tool Library",
    ]
    memberships = {
        (m["project_id"], m["role"]) for m in client.get("/api/v1/me").json()["memberships"]
    }
    assert {(created["id"], "editor"), (created["id"], "approver")} <= memberships
    with _session(seeded_database_url) as session:
        published = resolve_project_reader(session)(ProjectId(UUID(created["id"])))
    assert published is not None
    assert published.name == "Makerspace Tool Library"


def test_a_project_is_not_created_without_its_membership(
    seeded_database_url: str, make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_: object) -> None:
        raise RuntimeError("synthetic failure while granting roles")

    monkeypatch.setattr("scopesteps.identity.http.auth.SqlMemberships.grant", fail)
    client = make_client(seeded_database_url)

    with pytest.raises(RuntimeError, match="synthetic failure"):
        _create(client, "Makerspace Tool Library")

    assert _count(seeded_database_url, ProjectRecord) == 1
    assert _count(seeded_database_url, MembershipRecord) == 2


@pytest.mark.parametrize(
    ("name", "stored"),
    [
        ("x", "x"),
        ("n" * 80, "n" * 80),
        ("  " + "n" * 80 + "\n", "n" * 80),
        ("Library\tkiosk \n refresh", "Library kiosk refresh"),
    ],
    ids=["one-character", "eighty", "eighty-padded", "inner-whitespace"],
)
def test_valid_names_are_stored_trimmed(client: TestClient, name: str, stored: str) -> None:
    response = _create(client, name)

    assert response.status_code == 201
    assert response.json()["name"] == stored


@pytest.mark.parametrize(
    "name",
    ["", "   ", "\t\n", "n" * 81, " " + "n" * 81 + " "],
    ids=["blank", "spaces", "tabs", "eighty-one", "eighty-one-padded"],
)
def test_invalid_names_are_rejected_and_nothing_is_stored(
    seeded_database_url: str, make_client: ClientFactory, name: str
) -> None:
    client = make_client(seeded_database_url)

    created = _create(client, name)
    renamed = _rename(client, DEMO_URL, name)

    for response in (created, renamed):
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "PROJECT_NAME_INVALID"
        assert body["details"] == {"field": "name", "max_chars": 80}
        assert body["retryable"] is False
    assert _count(seeded_database_url, ProjectRecord) == 1
    assert client.get(DEMO_URL).json()["name"] == "Campus Room Booking"


@pytest.mark.parametrize(
    "body",
    [{}, {"name": None}, {"name": 7}],
    ids=["missing", "null", "number"],
)
def test_a_malformed_create_body_is_a_validation_error(client: TestClient, body: Json) -> None:
    response = client.post(PROJECTS_URL, json=body, headers={"Idempotency-Key": "create-key-0001"})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_a_rejected_create_can_be_corrected_under_the_same_key(client: TestClient) -> None:
    rejected = _create(client, "   ")

    corrected = _create(client, "Makerspace Tool Library")

    assert rejected.status_code == 422
    assert corrected.status_code == 201


def test_repeating_a_create_returns_the_same_project(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    client = make_client(seeded_database_url)
    first = _create(client, "Makerspace Tool Library")

    second = _create(client, " Makerspace Tool Library ")

    assert second.status_code == 201
    assert second.json() == first.json()
    assert _count(seeded_database_url, ProjectRecord) == 2
    assert _count(seeded_database_url, MembershipRecord) == 4


def test_reusing_a_create_key_for_another_name_is_a_conflict(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    client = make_client(seeded_database_url)
    _create(client, "Makerspace Tool Library")

    response = _create(client, "Library Kiosk Refresh")

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert _count(seeded_database_url, ProjectRecord) == 2


def test_two_projects_may_share_a_name(client: TestClient) -> None:
    first = _create(client, "Campus Room Booking", key="create-key-0001")
    second = _create(client, "Campus Room Booking", key="create-key-0002")

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["id"] != second.json()["id"]
    assert len(_listed(client)) == 3


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("post", PROJECTS_URL, {"name": "Makerspace Tool Library"}),
        ("patch", DEMO_URL, {"name": "Study Rooms", "expected_revision": 1}),
    ],
    ids=["create", "rename"],
)
def test_commands_require_an_idempotency_key(
    client: TestClient, method: str, url: str, body: Json
) -> None:
    response = client.request(method, url, json=body)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert client.get(DEMO_URL).json()["name"] == "Campus Room Booking"
    assert len(_listed(client)) == 1


@pytest.mark.parametrize("role", MEMBER_ROLES)
def test_any_member_reads_the_project_with_its_limits(
    seeded_database_url: str, make_client: ClientFactory, role: Role
) -> None:
    url = _add_project(seeded_database_url, role)

    response = make_client(seeded_database_url).get(url)

    assert response.status_code == 200
    project = response.json()
    assert project["name"] == "Makerspace Tool Library"
    assert project["roles"] == [role.value]
    assert project["status"]["state"] == "no_baseline"
    assert project["limits"] == {
        "project_name_max_chars": 80,
        "source": {"max_bytes": 512 * 1024, "max_words": 6000},
        "run": {"max_turns": 6, "max_tool_calls": 8, "max_clarification_rounds": 2},
        "backlog": {"max_epics": 2, "max_stories": 8},
    }


def test_the_limits_are_the_configured_ones(
    seeded_database_url: str, monkeypatch: pytest.MonkeyPatch, make_client: ClientFactory
) -> None:
    monkeypatch.setenv("SOURCE_MAX_WORDS", "1200")
    monkeypatch.setenv("RUN_MAX_TURNS", "3")
    monkeypatch.setenv("RUN_MAX_CLARIFICATION_ROUNDS", "1")

    limits = make_client(seeded_database_url).get(DEMO_URL).json()["limits"]

    assert limits["source"]["max_words"] == 1200
    assert limits["run"] == {"max_turns": 3, "max_tool_calls": 8, "max_clarification_rounds": 1}


def test_a_project_the_actor_is_not_a_member_of_looks_unknown(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    url = _add_project(seeded_database_url)
    client = make_client(seeded_database_url)

    hidden = [client.get(url), _rename(client, url, "Study Rooms")]
    unknown = [
        client.get(f"{PROJECTS_URL}/{new_id()}"),
        _rename(client, f"{PROJECTS_URL}/{new_id()}", "Study Rooms"),
    ]

    for response in hidden + unknown:
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"
    assert hidden[0].json()["message"] == unknown[0].json()["message"]
    assert hidden[1].json()["message"] == unknown[1].json()["message"]


@pytest.mark.parametrize("role", [Role.EDITOR, Role.APPROVER])
def test_editors_and_approvers_can_rename(
    seeded_database_url: str, make_client: ClientFactory, role: Role
) -> None:
    url = _add_project(seeded_database_url, role)
    client = make_client(seeded_database_url)

    response = _rename(client, url, "  Makerspace Tool Library 2027 ")

    assert response.status_code == 200
    renamed = response.json()
    assert renamed["name"] == "Makerspace Tool Library 2027"
    assert renamed["revision"] == 2
    assert renamed["roles"] == [role.value]
    assert client.get(url).json() == renamed


def test_viewers_can_read_but_not_rename(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    url = _add_project(seeded_database_url, Role.VIEWER)
    client = make_client(seeded_database_url)

    response = _rename(client, url, "Study Rooms")

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert client.get(url).json()["name"] == "Makerspace Tool Library"


def test_a_stale_rename_is_a_conflict_and_changes_nothing(client: TestClient) -> None:
    _rename(client, DEMO_URL, "Campus Room Booking 2027", key="rename-key-0001")

    response = _rename(client, DEMO_URL, "Study Rooms", expected_revision=1, key="rename-key-0002")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "PROJECT_CHANGED"
    assert body["details"] == {"current_revision": 2}
    assert body["retryable"] is False
    current = client.get(DEMO_URL).json()
    assert (current["name"], current["revision"]) == ("Campus Room Booking 2027", 2)


def test_a_rename_with_the_current_revision_succeeds_after_a_conflict(client: TestClient) -> None:
    _rename(client, DEMO_URL, "Campus Room Booking 2027", key="rename-key-0001")
    _rename(client, DEMO_URL, "Study Rooms", expected_revision=1, key="rename-key-0002")

    response = _rename(client, DEMO_URL, "Study Rooms", expected_revision=2, key="rename-key-0003")

    assert response.status_code == 200
    assert (response.json()["name"], response.json()["revision"]) == ("Study Rooms", 3)


def test_repeating_a_rename_returns_the_project_without_renaming_twice(client: TestClient) -> None:
    first = _rename(client, DEMO_URL, "Campus Room Booking 2027")

    second = _rename(client, DEMO_URL, "Campus Room Booking 2027")

    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.json()["revision"] == 2


def test_reusing_a_rename_key_for_another_request_is_a_conflict(client: TestClient) -> None:
    _rename(client, DEMO_URL, "Campus Room Booking 2027")

    response = _rename(client, DEMO_URL, "Study Rooms", expected_revision=2)

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert client.get(DEMO_URL).json()["name"] == "Campus Room Booking 2027"


@pytest.mark.parametrize("expected_revision", [0, -1, None, "one"])
def test_a_rename_needs_a_positive_expected_revision(
    client: TestClient, expected_revision: object
) -> None:
    response = client.patch(
        DEMO_URL,
        json={"name": "Study Rooms", "expected_revision": expected_revision},
        headers={"Idempotency-Key": "rename-key-0001"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_a_renamed_project_survives_an_application_restart(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    _rename(make_client(seeded_database_url), DEMO_URL, "Campus Room Booking 2027")

    restarted = make_client(seeded_database_url).get(DEMO_URL).json()

    assert (restarted["name"], restarted["revision"]) == ("Campus Room Booking 2027", 2)


def test_non_loopback_clients_cannot_reach_projects(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    client = make_client(seeded_database_url, client=("203.0.113.7", 50000))

    responses = [client.get(PROJECTS_URL), client.get(DEMO_URL), _create(client, "Study Rooms")]

    assert [response.status_code for response in responses] == [403, 403, 403]


def _activity(client: TestClient, url: str = DEMO_URL) -> list[Json]:
    response = client.get(f"{url}/activity")
    assert response.status_code == 200
    events: list[Json] = response.json()["events"]
    return events


def test_a_rename_appears_in_the_activity_feed(client: TestClient) -> None:
    _rename(client, DEMO_URL, "Campus Room Booking 2027")

    (event,) = _activity(client)

    assert event == {
        "id": event["id"],
        "project_id": str(DEMO_PROJECT_ID),
        "type": "project.renamed",
        "actor": {
            "kind": "user",
            "user_id": str(LOCAL_REVIEWER_ID),
            "display_name": "Local Reviewer",
        },
        "subjects": [{"kind": "project", "id": str(DEMO_PROJECT_ID)}],
        "summary": 'Renamed the project from "Campus Room Booking" to "Campus Room Booking 2027"',
        "occurred_at": event["occurred_at"],
    }


def test_only_renames_that_change_the_name_are_recorded(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    read_only = _add_project(seeded_database_url, Role.VIEWER)
    client = make_client(seeded_database_url)

    unchanged = _rename(client, DEMO_URL, " Campus Room Booking ", key="rename-key-0001")
    renamed = _rename(client, DEMO_URL, "Study Rooms", key="rename-key-0002")
    replayed = _rename(client, DEMO_URL, "Study Rooms", key="rename-key-0002")
    stale = _rename(client, DEMO_URL, "Reading Rooms", key="rename-key-0003")
    invalid = _rename(client, DEMO_URL, "   ", expected_revision=2, key="rename-key-0004")
    forbidden = _rename(client, read_only, "Study Rooms", key="rename-key-0005")
    created = _create(client, "Makerspace Tool Library")

    outcomes = (unchanged, renamed, replayed, stale, invalid, forbidden)
    assert [response.status_code for response in outcomes] == [200, 200, 200, 409, 422, 403]
    assert [event["summary"] for event in _activity(client)] == [
        'Renamed the project from "Campus Room Booking" to "Study Rooms"'
    ]
    assert _activity(client, read_only) == []
    assert _activity(client, f"{PROJECTS_URL}/{created.json()['id']}") == []


def test_the_longest_names_can_be_renamed_and_recorded(client: TestClient) -> None:
    first = _rename(client, DEMO_URL, "a" * 80, key="rename-key-0001")

    second = _rename(client, DEMO_URL, "b" * 80, expected_revision=2, key="rename-key-0002")

    assert (first.status_code, second.status_code) == (200, 200)
    assert len(_activity(client)) == 2
