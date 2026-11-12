"""Publishing approved versions to Jira, against a fake Jira Cloud site (ADR 0029).

The fake answers the REST v3 calls publishing makes, held in memory; no test reaches the network.
Switches make it refuse, rate-limit or time out the way the real service does, so the outbox's
recovery is tested. Backlogs are synthetic.
"""

import base64
import json
import logging
import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from scopesteps.api.jira_check import run as run_jira_check
from scopesteps.api.notification_job import NotificationJob
from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID
from scopesteps.backlog.client import (
    BacklogVersionId,
    CandidateProposal,
    Evidence,
    ProposedCriterion,
    ProposedItem,
    save_candidate,
)
from scopesteps.backlog.infrastructure.orm import VersionRecord
from scopesteps.identity.application.users import grant_project_role
from scopesteps.identity.client import Role
from scopesteps.identity.infrastructure.email import RecordingEmailSender
from scopesteps.identity.infrastructure.orm import MembershipRecord
from scopesteps.identity.infrastructure.repository import SqlUserDirectory, SqlUserRepository
from scopesteps.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    utc_now,
)
from scopesteps.jira_integration.client import (
    JiraRuntime,
    PublishId,
    jira_runtime,
    send_due_publishes,
)
from scopesteps.jira_integration.infrastructure.jira_http import HttpJiraGateway
from scopesteps.jira_integration.infrastructure.orm import ConnectionRecord, IssueLinkRecord
from scopesteps.jira_integration.infrastructure.repository import SqlJiraStore
from scopesteps.kernel.ids import new_id
from scopesteps.notifications.infrastructure.orm import NotificationRecord
from scopesteps.projects.client import ProjectId

SITE = "https://synthetic-team.atlassian.net"
EMAIL = "pm@example.test"
TOKEN = "synthetic-api-token-0001"  # noqa: S105 - the fake site's, not a real one
PROJECT_KEY = "ROOM"
EPIC, STORY, SUBTASK = "10000", "10001", "10003"
DONE_TRANSITION = "31"

Json = dict[str, Any]


@dataclass
class FakeIssue:
    id: str
    key: str
    type_id: str
    summary: str
    description: Json
    parent_key: str | None
    done: bool = False

    def text(self) -> str:
        return json.dumps(self.description)


@dataclass
class FakeJira:
    issues: dict[str, FakeIssue] = field(default_factory=dict[str, FakeIssue])
    calls: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    """Every request as (method, path), oldest first."""
    refuse_summaries: set[str] = field(default_factory=set[str])
    """A create or update with one of these summaries gets a 400."""
    rate_limit_next: int = 0
    revoked: bool = False
    """The token was revoked or expired in Jira: every request gets a 401."""
    unavailable: bool = False
    """Every request gets a 503, as when Jira is down."""
    """How many of the next requests get a 429."""
    lose_next_create: bool = False
    """The next create is stored, but its answer never arrives (a timeout)."""
    no_done_status: bool = False
    has_subtasks: bool = True

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def writes(self) -> list[tuple[str, str]]:
        return [
            call for call in self.calls if call[0] in ("POST", "PUT") and "search" not in call[1]
        ]

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/rest/api/3")
        self.calls.append((request.method, path))
        if request.url.host != SITE.removeprefix("https://"):
            raise httpx.ConnectError("unknown host", request=request)
        if self.revoked or request.headers.get("Authorization") != _basic(EMAIL, TOKEN):
            return httpx.Response(401, json={"errorMessages": ["Unauthorized"]})
        if self.unavailable:
            return httpx.Response(503)
        if self.rate_limit_next:
            self.rate_limit_next -= 1
            return httpx.Response(429, headers={"Retry-After": "30"})
        body: Json = json.loads(request.content) if request.content else {}
        return self._route(request.method, path, body, request)

    def _route(self, method: str, path: str, body: Json, request: httpx.Request) -> httpx.Response:
        if (method, path) == ("GET", "/myself"):
            return httpx.Response(
                200,
                json={
                    "accountId": "5b10-synthetic-bot",
                    "displayName": "ScopeSteps Bot",
                    "emailAddress": EMAIL,
                },
            )
        if method == "GET" and path == f"/project/{PROJECT_KEY}":
            return httpx.Response(200, json={"id": "10010", "key": PROJECT_KEY, "name": "Rooms"})
        if method == "GET" and path.startswith("/project/"):
            return httpx.Response(404, json={"errorMessages": ["No project"]})
        if method == "GET" and path == f"/issue/createmeta/{PROJECT_KEY}/issuetypes":
            types = [
                {"id": EPIC, "name": "Epic", "subtask": False, "hierarchyLevel": 1},
                {"id": STORY, "name": "Story", "subtask": False, "hierarchyLevel": 0},
            ]
            if self.has_subtasks:
                types.append(
                    {"id": SUBTASK, "name": "Subtask", "subtask": True, "hierarchyLevel": -1}
                )
            return httpx.Response(200, json={"issueTypes": types})
        if (method, path) == ("POST", "/issue"):
            return self._create(body["fields"], request)
        if (method, path) == ("POST", "/search/jql"):
            marker = re.search(r'\\"(.+)\\"', body["jql"])
            found = [
                {"id": issue.id, "key": issue.key}
                for issue in self.issues.values()
                if marker and marker.group(1) in issue.text()
            ]
            return httpx.Response(200, json={"issues": found[:1]})
        match = re.fullmatch(r"/issue/([A-Z]+-\d+)(/transitions)?", path)
        if match is None or match.group(1) not in self.issues:
            return httpx.Response(404, json={"errorMessages": ["No issue"]})
        issue = self.issues[match.group(1)]
        if match.group(2):
            if method == "GET":
                listed = (
                    []
                    if self.no_done_status
                    else [{"id": DONE_TRANSITION, "to": {"statusCategory": {"key": "done"}}}]
                )
                return httpx.Response(200, json={"transitions": listed})
            issue.done = body["transition"]["id"] == DONE_TRANSITION
            return httpx.Response(204)
        if method == "GET":
            category = "done" if issue.done else "new"
            return httpx.Response(
                200, json={"fields": {"status": {"statusCategory": {"key": category}}}}
            )
        fields = body["fields"]
        if fields["summary"] in self.refuse_summaries:
            return httpx.Response(400, json={"errors": {"summary": f"refused {fields['summary']}"}})
        issue.summary = fields["summary"]
        if "description" in fields:
            issue.description = fields["description"]
        if "parent" in fields:
            issue.parent_key = fields["parent"]["key"]
        return httpx.Response(204)

    def _create(self, fields: Json, request: httpx.Request) -> httpx.Response:
        if fields["summary"] in self.refuse_summaries:
            return httpx.Response(400, json={"errors": {"summary": f"refused {fields['summary']}"}})
        number = len(self.issues) + 1
        issue = FakeIssue(
            id=str(20000 + number),
            key=f"{PROJECT_KEY}-{number}",
            type_id=fields["issuetype"]["id"],
            summary=fields["summary"],
            description=fields["description"],
            parent_key=fields.get("parent", {}).get("key"),
        )
        self.issues[issue.key] = issue
        if self.lose_next_create:
            self.lose_next_create = False
            raise httpx.ReadTimeout("no answer", request=request)
        return httpx.Response(201, json={"id": issue.id, "key": issue.key})

    def by_summary(self, summary: str) -> list[FakeIssue]:
        return [issue for issue in self.issues.values() if issue.summary == summary]


def _basic(email: str, token: str) -> str:
    return "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()


# --- The project, its backlog and its Jira connection -------------------------------------------

PROJECT = f"/api/v1/projects/{DEMO_PROJECT_ID}"
KEY = Fernet.generate_key().decode()
CONNECT = {
    "site_url": "synthetic-team.atlassian.net",
    "email": EMAIL,
    "api_token": TOKEN,
    "project_key": "room",
}


@contextmanager
def _session(database_url: str) -> Generator[Session]:
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        yield session
        session.commit()
    engine.dispose()


class Project:
    """The demo project with approved versions made as a run and an approver make them."""

    def __init__(self, client: TestClient, database_url: str, jira: FakeJira) -> None:
        self.client = client
        self.database_url = database_url
        self.jira = jira
        self.keys = 0
        client.app.state.jira_runtime = jira_runtime(  # type: ignore[attr-defined]
            KEY, "https://app.scopesteps.test", jira.transport(), directory=SqlUserDirectory
        )
        uploaded = client.post(
            f"{PROJECT}/sources",
            files={"brief": ("brief.md", b"# Rooms\n\nStudents book study rooms.")},
            headers={"Idempotency-Key": "jira-upload-0001"},
        )
        assert uploaded.status_code == 201, uploaded.text
        self.brief = UUID(uploaded.json()["source_versions"][0]["id"])
        blocks = client.get(f"{PROJECT}/sources/{self.brief}/blocks").json()
        self.block = UUID(blocks[1]["id"])

    def key(self) -> str:
        self.keys += 1
        return f"jira-test-key-{self.keys:04d}"

    def connect(self, **changes: str) -> dict[str, Any]:
        response = self.client.put(f"{PROJECT}/jira/connection", json={**CONNECT, **changes})
        assert response.status_code == 200, response.text
        return response.json()

    def draft(
        self, stories: dict[str, list[str]], base: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """A draft of one epic with `stories` (title: its tasks), each with one criterion."""
        proposal = CandidateProposal(
            project_id=DEMO_PROJECT_ID,
            run_id=new_id(),
            created_by=LOCAL_REVIEWER_ID,
            source_version_ids=(self.brief,),
            items=(
                ProposedItem("E1", "epic", None, "Room booking", "Booking study rooms."),
                *(
                    ProposedItem(
                        f"S{n}",
                        "story",
                        "E1",
                        title,
                        f"As a student, I want to {title.lower()}.",
                        criteria=(
                            ProposedCriterion(
                                f"{title} works.",
                                proposed=False,
                                evidence=(Evidence(self.brief, self.block, "book study rooms"),),
                            ),
                        ),
                    )
                    for n, title in enumerate(stories, start=1)
                ),
            ),
        )
        with _session(self.database_url) as session:
            version_id = save_candidate(session, proposal, utc_now())
            if base is not None:
                record = session.get_one(VersionRecord, version_id)
                record.base_version_id = BacklogVersionId(UUID(base["id"]))
        draft = self.get(version_id)
        for story in [item for item in draft["items"] if item["kind"] == "story"]:
            tasks = [{"id": None, "title": title} for title in stories[story["title"]]]
            if tasks:
                response = self.client.patch(
                    f"/api/v1/backlogs/{draft['id']}/items/{story['id']}",
                    json={"expected_revision": draft["revision"], "tasks": tasks},
                    headers={"Idempotency-Key": self.key()},
                )
                assert response.status_code == 200, response.text
                draft = response.json()
        return draft

    def get(self, version_id: object) -> dict[str, Any]:
        response = self.client.get(f"{PROJECT}/backlogs/{version_id}")
        assert response.status_code == 200, response.text
        return response.json()

    def approve(
        self, draft: dict[str, Any], baseline: dict[str, Any] | None = None, **extra: object
    ) -> dict[str, Any]:
        response = self.client.post(
            f"/api/v1/backlogs/{draft['id']}/approve",
            json={
                "expected_revision": draft["revision"],
                "content_hash": draft["content_hash"],
                "expected_baseline_id": None if baseline is None else baseline["id"],
                **extra,
            },
            headers={"Idempotency-Key": self.key()},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def approved(
        self, stories: dict[str, list[str]], baseline: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        draft = self.draft(stories, base=baseline)
        self.approve(draft, baseline)
        return self.get(draft["id"])

    def start(self, version: dict[str, Any], key: str | None = None) -> Response:
        return self.client.post(
            f"{PROJECT}/jira/publishes",
            json={"version_id": version["id"]},
            headers={"Idempotency-Key": key or self.key()},
        )

    def advance(self, publish: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(f"/api/v1/jira/publishes/{publish['id']}/advance")
        assert response.status_code == 200, response.text
        return response.json()

    def publish(self, version: dict[str, Any]) -> dict[str, Any]:
        """Starts a publish and advances it until it stops sending."""
        started = self.start(version)
        assert started.status_code == 201, started.text
        return self.publish_until_finished(started.json())

    def publish_until_finished(self, publish: dict[str, Any]) -> dict[str, Any]:
        """Advances a publish until it stops sending."""
        for _ in range(20):
            if publish["status"] != "sending":
                return publish
            publish = self.advance(publish)
        raise AssertionError("the publish never finished")

    def background_round(self, at: datetime | None = None) -> int:
        """One round of the server's background sender, as if it ran at `at`."""
        runtime: JiraRuntime = cast(FastAPI, self.client.app).state.jira_runtime
        moment = at or utc_now()
        return send_due_publishes(self.session_factory, runtime, lambda: moment)

    @property
    def session_factory(self) -> sessionmaker[Session]:
        factory: sessionmaker[Session] = cast(FastAPI, self.client.app).state.session_factory
        return factory

    def get_publish(self, publish: dict[str, Any]) -> dict[str, Any]:
        return self.client.get(f"/api/v1/jira/publishes/{publish['id']}").json()

    def links(self) -> dict[str, dict[str, Any]]:
        response = self.client.get(f"{PROJECT}/jira/issues")
        assert response.status_code == 200, response.text
        return {link["item_id"]: link for link in response.json()["issues"]}

    def hold_role(self, role: Role) -> None:
        with _session(self.database_url) as session:
            session.execute(
                delete(MembershipRecord).where(
                    MembershipRecord.user_id == LOCAL_REVIEWER_ID,
                    MembershipRecord.project_id == DEMO_PROJECT_ID,
                )
            )
            grant_project_role(
                SqlUserRepository(session),
                LOCAL_REVIEWER_ID,
                ProjectId(DEMO_PROJECT_ID),
                role,
                utc_now(),
            )

    def activity(self) -> list[dict[str, Any]]:
        return self.client.get(f"{PROJECT}/activity").json()["events"]


@pytest.fixture
def jira() -> FakeJira:
    return FakeJira()


@pytest.fixture
def project(
    client: TestClient,
    seeded_database_url: str,
    jira: FakeJira,
    confirm_speakers: Callable[[TestClient], None],
) -> Project:
    made = Project(client, seeded_database_url, jira)
    confirm_speakers(client)
    return made


STORIES = {"Search rooms": ["Build the search form"], "Book a slot": ["Build the overlap check"]}


def _story(version: dict[str, Any], title: str) -> dict[str, Any]:
    return next(item for item in version["items"] if item.get("title") == title)


# --- Connecting -----------------------------------------------------------------------------------


def test_connecting_tests_the_details_and_never_returns_or_stores_the_token_in_plain_text(
    project: Project, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    saved = project.connect()
    shown = project.client.get(f"{PROJECT}/jira/connection")

    assert saved["site_url"] == SITE
    assert (saved["jira_project_key"], saved["auto_publish"], saved["revision"]) == (
        "ROOM",
        False,
        1,
    )
    assert TOKEN not in json.dumps(saved)
    assert TOKEN not in shown.text
    assert shown.json()["configured"] is True
    assert ("GET", "/myself") in project.jira.calls
    with _session(project.database_url) as session:
        record = session.scalars(select(ConnectionRecord)).one()
        assert TOKEN.encode() not in record.token_ciphertext
    assert TOKEN not in caplog.text
    assert any(event["type"] == "jira.connected" for event in project.activity())


@pytest.mark.parametrize(
    ("changes", "status", "code"),
    [
        ({"api_token": "wrong-token"}, 422, "JIRA_AUTH_FAILED"),
        ({"project_key": "NOPE"}, 422, "JIRA_PROJECT_NOT_FOUND"),
        ({"site_url": "http://localhost:8000"}, 422, "JIRA_SITE_INVALID"),
        ({"site_url": "https://169.254.169.254"}, 422, "JIRA_SITE_INVALID"),
        ({"project_key": "x"}, 422, "VALIDATION_ERROR"),
    ],
)
def test_refused_details_save_nothing(
    project: Project, changes: dict[str, str], status: int, code: str
) -> None:
    response = project.client.put(f"{PROJECT}/jira/connection", json={**CONNECT, **changes})

    assert (response.status_code, response.json()["code"]) == (status, code)
    assert "wrong-token" not in response.text
    assert project.client.get(f"{PROJECT}/jira/connection").json()["connection"] is None


def test_a_project_without_sub_tasks_is_refused(project: Project) -> None:
    project.jira.has_subtasks = False

    response = project.client.put(f"{PROJECT}/jira/connection", json=CONNECT)

    assert response.json()["code"] == "JIRA_PROJECT_UNSUITABLE"


def test_without_a_token_key_jira_cannot_be_connected(project: Project) -> None:
    project.client.app.state.jira_runtime = jira_runtime(  # type: ignore[attr-defined]
        None, "https://app.scopesteps.test", project.jira.transport(), directory=SqlUserDirectory
    )

    response = project.client.put(f"{PROJECT}/jira/connection", json=CONNECT)

    assert (response.status_code, response.json()["code"]) == (503, "JIRA_NOT_CONFIGURED")
    assert project.client.get(f"{PROJECT}/jira/connection").json()["configured"] is False


def test_settings_default_off_change_with_the_revision_and_disconnect_deletes_the_token(
    project: Project,
) -> None:
    connection = project.connect()

    turned_on = project.client.patch(
        f"{PROJECT}/jira/connection", json={"auto_publish": True, "expected_revision": 1}
    )
    stale = project.client.patch(
        f"{PROJECT}/jira/connection", json={"auto_publish": False, "expected_revision": 1}
    )
    tested = project.client.post(f"{PROJECT}/jira/connection/test")
    removed = project.client.delete(f"{PROJECT}/jira/connection")

    assert connection["auto_publish"] is False
    assert turned_on.json()["auto_publish"] is True
    assert (stale.status_code, stale.json()["code"]) == (409, "CONNECTION_CHANGED")
    assert tested.status_code == 200
    assert removed.status_code == 204
    with _session(project.database_url) as session:
        assert session.scalars(select(ConnectionRecord)).all() == []
    types = [event["type"] for event in project.activity()]
    assert {"jira.settings_changed", "jira.disconnected"} <= set(types)


# --- Preview and the first publish ----------------------------------------------------------------


def test_the_preview_counts_what_would_happen_and_sends_nothing(project: Project) -> None:
    project.connect()
    version = project.approved(STORIES)
    calls_before = len(project.jira.calls)

    preview = project.client.get(f"{PROJECT}/jira/preview", params={"version_id": version["id"]})

    assert preview.status_code == 200, preview.text
    counts = {row["kind"]: row for row in preview.json()["counts"]}
    assert (counts["epic"]["create"], counts["story"]["create"], counts["task"]["create"]) == (
        1,
        2,
        2,
    )
    assert len(project.jira.calls) == calls_before


def test_the_first_publish_creates_epics_stories_and_sub_tasks_with_parents_and_criteria(
    project: Project,
) -> None:
    project.connect()
    version = project.approved(STORIES)

    publish = project.publish(version)

    assert (publish["status"], publish["sent"], publish["total"], publish["failed"]) == (
        "done",
        5,
        5,
        [],
    )
    epic = project.jira.by_summary("Room booking")[0]
    story = project.jira.by_summary("Book a slot")[0]
    task = project.jira.by_summary("Build the overlap check")[0]
    assert (epic.type_id, story.type_id, task.type_id) == (EPIC, STORY, SUBTASK)
    assert (story.parent_key, task.parent_key) == (epic.key, story.key)
    assert "Book a slot works." in story.text()
    assert "Acceptance criteria" in story.text()
    assert f"{'https://app.scopesteps.test'}/projects/{DEMO_PROJECT_ID}/backlog" in story.text()
    links = project.links()
    story_id = _story(version, "Book a slot")["id"]
    assert links[story_id]["jira_key"] == story.key
    assert links[story_id]["url"] == f"{SITE}/browse/{story.key}"
    event = next(e for e in project.activity() if e["type"] == "jira.published")
    assert event["summary"] == "Published to Jira: 5 created, 0 updated, 0 closed"
    assert event["actor"]["user_id"] == str(LOCAL_REVIEWER_ID)
    assert event["subjects"] == [{"kind": "backlog_version", "id": version["id"]}]


def test_drafts_and_proposed_versions_can_never_be_published(project: Project) -> None:
    project.connect()
    draft = project.draft(STORIES)

    preview = project.client.get(f"{PROJECT}/jira/preview", params={"version_id": draft["id"]})
    started = project.start(draft)

    assert (preview.status_code, preview.json()["code"]) == (409, "VERSION_NOT_APPROVED")
    assert (started.status_code, started.json()["code"]) == (409, "VERSION_NOT_APPROVED")
    assert project.jira.writes() == []


def test_publishing_needs_a_connection(project: Project) -> None:
    version = project.approved(STORIES)

    started = project.start(version)

    assert (started.status_code, started.json()["code"]) == (409, "JIRA_NOT_CONNECTED")


# --- Later versions -------------------------------------------------------------------------------


def test_a_later_version_updates_changed_issues_creates_new_ones_and_closes_removed_ones(
    project: Project,
) -> None:
    project.connect()
    v1 = project.approved(STORIES)
    project.publish(v1)
    first_keys = {issue.key for issue in project.jira.issues.values()}
    writes_before = len(project.jira.writes())

    v2 = project.approved(
        {"Search rooms": ["Build the search form"], "Cancel a booking": []}, baseline=v1
    )
    preview = project.client.get(f"{PROJECT}/jira/preview", params={"version_id": v2["id"]}).json()
    publish = project.publish(v2)

    counts = {row["kind"]: row for row in preview["counts"]}
    # v2 is a new draft, so its items have new ids: everything of v1 closes, v2's is created.
    assert counts["story"]["create"] == 2
    assert counts["story"]["close"] == 2
    assert publish["status"] == "done"
    closed = [issue for issue in project.jira.issues.values() if issue.done]
    assert {issue.key for issue in closed} == first_keys - {
        issue.key for issue in project.jira.issues.values() if not issue.done
    }
    assert len(project.jira.issues) >= len(first_keys)  # nothing was deleted
    assert len(project.jira.writes()) > writes_before


def test_a_changed_item_updates_its_issue_and_an_unchanged_one_is_left_alone(
    project: Project,
) -> None:
    project.connect()
    draft = project.draft(STORIES)
    project.approve(draft)
    v1 = project.get(draft["id"])
    project.publish(v1)
    story = _story(v1, "Book a slot")
    key = project.links()[story["id"]]["jira_key"]
    _drift(project, story["id"])
    puts_before = [call for call in project.jira.writes() if call[0] == "PUT"]

    publish = project.publish(v1)

    puts = [call for call in project.jira.writes() if call[0] == "PUT"]
    assert publish["status"] == "done"
    assert puts[len(puts_before) :] == [("PUT", f"/issue/{key}")]
    assert project.jira.issues[key].summary == "Book a slot"


def _drift(project: Project, item_id: str) -> None:
    """Make what was published differ from the version, as an approved rewording of the story
    would: its stored fingerprint no longer matches."""
    with _session(project.database_url) as session:
        record = session.get_one(IssueLinkRecord, (DEMO_PROJECT_ID, UUID(item_id)))
        record.fingerprint = "0" * 64


def test_publishing_a_changed_task_again_keeps_the_teams_notes_in_its_subtask(
    project: Project,
) -> None:
    project.connect()
    version = project.approved(STORIES)
    project.publish(version)
    story = _story(version, "Book a slot")
    task_id = story["tasks"][0]["id"]
    links = project.links()
    subtask = project.jira.issues[links[task_id]["jira_key"]]
    story_issue = project.jira.issues[links[story["id"]]["jira_key"]]
    subtask.description = {
        "type": "doc",
        "version": 1,
        "content": [{"type": "text", "text": "Team note: reuse the calendar library."}],
    }
    story_issue.description = {"type": "doc", "version": 1, "content": []}
    _drift(project, task_id)
    _drift(project, story["id"])
    puts_before = len([c for c in project.jira.writes() if c[0] == "PUT"])

    publish = project.publish(version)

    puts = [c for c in project.jira.writes() if c[0] == "PUT"][puts_before:]
    assert publish["status"] == "done"
    assert sorted(puts) == sorted(
        [("PUT", f"/issue/{subtask.key}"), ("PUT", f"/issue/{story_issue.key}")]
    )
    assert "Team note: reuse the calendar library." in subtask.text()
    assert "Book a slot works." in story_issue.text()  # the story is ScopeSteps': rewritten


# --- Never twice ----------------------------------------------------------------------------------


def test_a_double_click_or_a_retry_publishes_once(project: Project) -> None:
    project.connect()
    version = project.approved(STORIES)

    first = project.start(version, key="same-click-key-01")
    again = project.start(version, key="same-click-key-01")
    other_tab = project.start(version)
    project.advance(first.json())
    project.advance(first.json())
    done = project.advance(first.json())

    assert first.json()["id"] == again.json()["id"] == other_tab.json()["id"]
    assert done["status"] == "done"
    assert len(project.jira.issues) == 5


def test_a_create_whose_answer_was_lost_is_found_again_not_created_twice(project: Project) -> None:
    project.connect()
    version = project.approved(STORIES)
    project.jira.lose_next_create = True

    started = project.start(version).json()
    stopped = project.advance(started)
    too_soon = project.advance(stopped)
    while project.background_round(utc_now() + timedelta(hours=1)):
        pass
    finished = project.get_publish(started)

    assert (stopped["status"], stopped["last_error"], stopped["sent"]) == (
        "sending",
        "JIRA_UNAVAILABLE",
        0,
    )
    assert stopped["next_attempt_at"] is not None
    assert too_soon["revision"] == stopped["revision"]  # waiting: nothing was sent
    assert finished["status"] == "done"
    assert len(project.jira.by_summary("Room booking")) == 1
    assert len(project.jira.issues) == 5
    assert ("POST", "/search/jql") in project.jira.calls


def test_a_rate_limit_waits_as_long_as_jira_asks_then_goes_on(project: Project) -> None:
    project.connect()
    version = project.approved(STORIES)
    project.jira.rate_limit_next = 1

    started = project.start(version).json()
    paused = project.advance(started)
    waited = datetime.fromisoformat(paused["next_attempt_at"]) - datetime.fromisoformat(
        paused["finished_at"] or paused["created_at"]
    )
    project.background_round(utc_now() + timedelta(seconds=10))
    still_waiting = project.get_publish(started)
    while project.background_round(utc_now() + timedelta(seconds=40)):
        pass
    finished = project.get_publish(started)

    assert (paused["status"], paused["last_error"]) == ("sending", "JIRA_RATE_LIMITED")
    assert timedelta(seconds=25) < waited < timedelta(minutes=5)
    assert still_waiting["sent"] == 0
    assert (finished["status"], finished["last_error"]) == ("done", None)
    assert len(project.jira.issues) == 5


def test_items_jira_refuses_are_listed_and_a_retry_sends_only_those(project: Project) -> None:
    project.connect()
    version = project.approved(STORIES)
    project.jira.refuse_summaries = {"Book a slot"}

    failed = project.publish(version)
    project.jira.refuse_summaries = set()
    retried = project.client.post(f"/api/v1/jira/publishes/{failed['id']}/retry")
    finished = project.advance(retried.json())

    story_id = _story(version, "Book a slot")["id"]
    task_id = _story(version, "Book a slot")["tasks"][0]["id"]
    assert failed["status"] == "failed"
    assert {(f["item_id"], f["error_code"]) for f in failed["failed"]} == {
        (story_id, "JIRA_REJECTED"),
        (task_id, "PARENT_NOT_PUBLISHED"),
    }
    assert any(e["type"] == "jira.publish_failed" for e in project.activity())
    assert retried.status_code == 200
    assert retried.json()["status"] == "sending"
    assert finished["status"] == "done"
    assert finished["failed"] == []
    assert len(project.jira.issues) == 5
    assert len(project.jira.by_summary("Room booking")) == 1


def test_another_version_waits_while_a_publish_is_sending(project: Project) -> None:
    project.connect()
    v1 = project.approved(STORIES)
    project.start(v1)
    v2 = project.approved({"Search rooms": []}, baseline=v1)

    refused = project.start(v2)

    assert (refused.status_code, refused.json()["code"]) == (409, "PUBLISH_IN_PROGRESS")


# --- Approval -------------------------------------------------------------------------------------


def test_approving_with_also_publish_starts_a_publish_after_the_approval(project: Project) -> None:
    project.connect()

    decision = project.approve(project.draft(STORIES), also_publish_to_jira=True)

    assert decision["decision"] == "approved"
    publish_id = decision["jira_publish_id"]
    assert publish_id is not None
    assert decision["jira_problem"] is None
    publish = project.client.get(f"/api/v1/jira/publishes/{publish_id}").json()
    assert publish["version_id"] == decision["version_id"]
    assert publish["status"] == "sending"
    assert project.jira.writes() == []  # nothing is sent until it is advanced


def test_without_the_checkbox_or_auto_publish_approving_publishes_nothing(project: Project) -> None:
    project.connect()

    decision = project.approve(project.draft(STORIES))

    assert decision["jira_publish_id"] is None


def test_auto_publish_starts_a_publish_on_every_approval(project: Project) -> None:
    project.connect()
    project.client.patch(
        f"{PROJECT}/jira/connection", json={"auto_publish": True, "expected_revision": 1}
    )

    decision = project.approve(project.draft(STORIES))

    assert decision["jira_publish_id"] is not None


def test_asking_to_publish_without_a_connection_still_approves_and_says_why(
    project: Project,
) -> None:
    decision = project.approve(project.draft(STORIES), also_publish_to_jira=True)

    assert decision["decision"] == "approved"
    assert (decision["jira_publish_id"], decision["jira_problem"]) == (None, "JIRA_NOT_CONNECTED")


# --- Roles ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.VIEWER, Role.EDITOR])
def test_only_an_approver_connects_publishes_or_changes_settings(
    project: Project, role: Role
) -> None:
    project.connect()
    version = project.approved(STORIES)
    project.publish(version)
    project.hold_role(role)

    shown = project.client.get(f"{PROJECT}/jira/connection").json()
    refused = [
        project.client.put(f"{PROJECT}/jira/connection", json=CONNECT),
        project.client.patch(
            f"{PROJECT}/jira/connection", json={"auto_publish": True, "expected_revision": 1}
        ),
        project.client.delete(f"{PROJECT}/jira/connection"),
        project.client.get(f"{PROJECT}/jira/preview", params={"version_id": version["id"]}),
        project.start(version),
    ]
    links = project.client.get(f"{PROJECT}/jira/issues")
    csv = project.client.get(f"/api/v1/backlogs/{version['id']}/export", params={"format": "csv"})

    assert [response.status_code for response in refused] == [403] * len(refused)
    assert (shown["can_publish"], shown["can_manage"]) == (False, False)
    assert shown["connection"]["email"] is None
    assert links.status_code == 200
    assert len(links.json()["issues"]) == 5
    assert csv.status_code == 200


def test_editors_publish_once_an_approver_lets_them_but_still_cannot_connect(
    project: Project,
) -> None:
    project.connect()
    version = project.approved(STORIES)
    allowed = project.client.patch(
        f"{PROJECT}/jira/connection",
        json={"publishers": "approvers_and_editors", "expected_revision": 1},
    )
    project.hold_role(Role.EDITOR)

    shown = project.client.get(f"{PROJECT}/jira/connection").json()
    publish = project.publish(version)
    connecting = project.client.put(f"{PROJECT}/jira/connection", json=CONNECT)
    settings = project.client.patch(
        f"{PROJECT}/jira/connection", json={"auto_publish": True, "expected_revision": 2}
    )
    project.hold_role(Role.VIEWER)
    viewer = project.start(version)

    assert allowed.json()["publishers"] == "approvers_and_editors"
    assert (shown["can_publish"], shown["can_manage"]) == (True, False)
    assert publish["status"] == "done"
    assert (connecting.status_code, settings.status_code, viewer.status_code) == (403, 403, 403)
    summaries = [e["summary"] for e in project.activity() if e["type"] == "jira.settings_changed"]
    assert summaries == ["Let Editors publish to Jira"]


# --- The background sender ------------------------------------------------------------------------


def test_the_server_finishes_a_publish_with_no_page_open(project: Project) -> None:
    project.connect()
    version = project.approved(STORIES)

    started = project.start(version).json()
    rounds = 0
    while project.background_round():
        rounds += 1

    finished = project.get_publish(started)
    assert rounds >= 1
    assert (finished["status"], finished["sent"]) == ("done", 5)
    assert len(project.jira.issues) == 5
    assert project.background_round() == 0  # nothing left to do


def test_a_publish_one_sender_holds_is_not_taken_by_another(project: Project) -> None:
    project.connect()
    version = project.approved(STORIES)
    started = project.start(version).json()
    now = utc_now()

    with project.session_factory() as session:
        store = SqlJiraStore(session)
        first = store.claim_due_publish(now, now + timedelta(minutes=5))
        second = store.claim_due_publish(now, now + timedelta(minutes=5))
        by_id = store.claim_publish(PublishId(UUID(started["id"])), now, now + timedelta(minutes=5))
        after_expiry = store.claim_due_publish(
            now + timedelta(minutes=6), now + timedelta(minutes=11)
        )
        session.commit()

    assert first is not None
    assert first.id == UUID(started["id"])
    assert (second, by_id) == (None, None)
    assert after_expiry is not None  # a sender that died leaves its lease to run out


def test_an_item_sent_five_times_without_an_answer_fails_instead_of_trying_forever(
    project: Project,
) -> None:
    project.connect()
    version = project.approved({"Search rooms": []})
    project.jira.unavailable = True
    started = project.start(version).json()

    moment = utc_now()
    for _ in range(30):
        moment += timedelta(hours=1)
        project.background_round(moment)

    finished = project.get_publish(started)
    assert finished["status"] == "failed"
    # The epic never got an answer; its story, with no parent in Jira, was not sent at all.
    assert sorted(f["error_code"] for f in finished["failed"]) == [
        "JIRA_UNAVAILABLE",
        "PARENT_NOT_PUBLISHED",
    ]
    assert project.jira.issues == {}


# --- The Jira account and its token ---------------------------------------------------------------


def state_of(connection: dict[str, Any]) -> str:
    """The connection's token state, read apart so the comparison is not mistaken for a secret."""
    return str(connection["token_state"])


def _set_expiry(project: Project, expires_on: date) -> None:
    with _session(project.database_url) as session:
        session.scalars(select(ConnectionRecord)).one().token_expires_on = expires_on


def test_the_connection_names_the_jira_account_and_the_tokens_expiry(project: Project) -> None:
    expires = (utc_now() + timedelta(days=200)).date()

    saved = project.connect(token_expires_on=expires.isoformat())

    assert saved["jira_account_name"] == "ScopeSteps Bot"
    assert (saved["token_state"], saved["token_expires_on"]) == ("working", expires.isoformat())
    assert saved["token_days_left"] in (199, 200)
    event = next(e for e in project.activity() if e["type"] == "jira.connected")
    assert event["summary"] == "Connected Jira project ROOM as ScopeSteps Bot"


@pytest.mark.parametrize("days", [-1, 0, 401])
def test_an_expiry_date_in_the_past_or_beyond_a_year_is_refused(
    project: Project, days: int
) -> None:
    expires = (utc_now() + timedelta(days=days)).date()

    response = project.client.put(
        f"{PROJECT}/jira/connection", json={**CONNECT, "token_expires_on": expires.isoformat()}
    )

    assert response.status_code == 422
    assert project.client.get(f"{PROJECT}/jira/connection").json()["connection"] is None


def test_a_token_close_to_its_date_warns_and_a_past_date_stops_publishing(project: Project) -> None:
    project.connect()
    version = project.approved(STORIES)
    project.client.patch(
        f"{PROJECT}/jira/connection",
        json={
            "token_expires_on": (utc_now() + timedelta(days=10)).date().isoformat(),
            "expected_revision": 1,
        },
    )
    soon = project.client.get(f"{PROJECT}/jira/connection").json()["connection"]
    _set_expiry(project, (utc_now() - timedelta(days=1)).date())

    expired = project.client.get(f"{PROJECT}/jira/connection").json()["connection"]
    refused = project.start(version)

    assert (soon["token_state"], soon["token_days_left"]) in {
        ("expires_soon", 9),
        ("expires_soon", 10),
    }
    assert (expired["token_state"], expired["token_days_left"]) == ("expired", 0)
    assert (refused.status_code, refused.json()["code"]) == (409, "JIRA_TOKEN_EXPIRED")
    assert project.jira.writes() == []


def test_a_token_revoked_mid_publish_stops_it_and_a_working_token_lets_it_finish(
    project: Project,
) -> None:
    project.connect()
    version = project.approved(STORIES)
    started = project.start(version).json()
    project.jira.revoked = True

    stopped = project.advance(started)
    shown = project.client.get(f"{PROJECT}/jira/connection").json()["connection"]
    refused = project.start(project.approved({"Search rooms": []}, baseline=version))
    project.jira.revoked = False
    tested = project.client.post(f"{PROJECT}/jira/connection/test")
    retried = project.client.post(f"/api/v1/jira/publishes/{started['id']}/retry")
    while project.background_round():
        pass

    assert (stopped["status"], stopped["last_error"]) == ("failed", "JIRA_TOKEN_REJECTED")
    assert {f["error_code"] for f in stopped["failed"]} == {"JIRA_TOKEN_REJECTED"}
    assert state_of(shown) == "rejected"
    assert (refused.status_code, refused.json()["code"]) == (409, "JIRA_TOKEN_REJECTED")
    assert state_of(tested.json()) == "working"
    assert retried.status_code == 200
    assert project.get_publish(started)["status"] == "done"
    assert len(project.jira.issues) == 5


def test_a_failed_test_marks_the_token_rejected(project: Project) -> None:
    project.connect()
    project.jira.revoked = True

    tested = project.client.post(f"{PROJECT}/jira/connection/test")

    assert (tested.status_code, tested.json()["code"]) == (422, "JIRA_AUTH_FAILED")
    shown = project.client.get(f"{PROJECT}/jira/connection").json()["connection"]
    assert state_of(shown) == "rejected"


def test_the_background_sender_checks_each_token_once_a_day(project: Project) -> None:
    project.connect()
    project.jira.revoked = True
    calls = len(project.jira.calls)

    project.background_round(utc_now() + timedelta(hours=2))
    same_day = len(project.jira.calls)
    project.background_round(utc_now() + timedelta(days=2))
    project.background_round(utc_now() + timedelta(days=4))

    shown = project.client.get(f"{PROJECT}/jira/connection").json()["connection"]
    assert same_day == calls  # checked less than a day ago: nothing sent
    assert project.jira.calls[calls:] == [("GET", "/myself")]  # once, then it is known refused
    assert state_of(shown) == "rejected"


def test_the_live_check_creates_nests_updates_and_closes_three_test_issues(jira: FakeJira) -> None:
    said: list[str] = []

    keys = run_jira_check(
        HttpJiraGateway(SITE, EMAIL, TOKEN, jira.transport()), "ROOM", SITE, said.append
    )

    epic, story, task = (jira.issues[key] for key in keys)
    assert (epic.type_id, story.type_id, task.type_id) == (EPIC, STORY, SUBTASK)
    assert (story.parent_key, task.parent_key) == (epic.key, story.key)
    assert story.summary.endswith("(updated)")
    assert all(issue.done for issue in (epic, story, task))
    assert said[0] == "1. The token works. Publishing as: ScopeSteps Bot"
    assert all(TOKEN not in line for line in said)


# --- Telling people how it went -----------------------------------------------------------------


def _notifications(project: Project, kind: str | None = None) -> list[dict[str, Any]]:
    listed = project.client.get("/api/v1/me/notifications").json()["notifications"]
    return [n for n in listed if kind is None or n["kind"] == kind]


def _send_emails(project: Project, at: datetime | None = None) -> RecordingEmailSender:
    app = cast(FastAPI, project.client.app)
    mail = RecordingEmailSender()
    app.state.email_sender = mail
    cast(NotificationJob, app.state.notification_job).tick(at or utc_now())
    return mail


def _notified_users(project: Project, kind: str) -> set[UUID]:
    with _session(project.database_url) as session:
        return set(
            session.scalars(
                select(NotificationRecord.user_id).where(NotificationRecord.kind == kind)
            )
        )


def test_a_finished_publish_tells_who_started_it_in_the_app_with_counts_only(
    project: Project,
) -> None:
    project.connect()
    version = project.approved(STORIES)

    publish = project.publish(version)

    (notice,) = _notifications(project, "jira_published")
    assert notice["subject_id"] == publish["id"]
    assert notice["version_id"] == version["id"]
    assert (notice["thread_id"], notice["comment_id"]) == (None, None)
    assert notice["details"] == {
        "created": 5,
        "updated": 0,
        "closed": 0,
        "failed": 0,
        "sent": 5,
        "total": 5,
        "days_left": None,
    }
    assert _send_emails(project).sent == []  # a publish that worked is told in the app only


def test_a_failed_publish_emails_once_with_counts_and_a_link_never_titles(
    project: Project,
) -> None:
    project.connect()
    version = project.approved(STORIES)
    project.jira.refuse_summaries = {"Build the overlap check"}
    publish = project.publish(version)
    assert publish["status"] == "failed"

    (notice,) = _notifications(project, "jira_publish_failed")
    mail = _send_emails(project)
    project.client.post(f"/api/v1/jira/publishes/{publish['id']}/retry")
    project.publish_until_finished(project.get_publish(publish))
    again = _send_emails(project, utc_now() + timedelta(hours=1))

    assert notice["details"]["failed"] == 1
    assert notice["details"]["sent"] == 4
    (message,) = mail.sent
    assert message.to == "reviewer@scopesteps.local"
    assert message.subject.startswith("1 item did not reach Jira from ")
    assert f"/projects/{DEMO_PROJECT_ID}/backlog?version={version['id']}" in message.text
    for secret in ("Build the overlap check", "Search rooms", TOKEN, "refused"):
        assert secret not in message.text
        assert secret not in message.html
    assert len(_notifications(project, "jira_publish_failed")) == 1  # failing again tells nobody
    assert again.sent == []


def test_the_failure_email_can_be_turned_off_while_the_notice_stays(project: Project) -> None:
    project.client.put(
        "/api/v1/me/notification-settings",
        json={"email_on_mention": True, "email_on_reply": False, "email_on_jira_failure": False},
    )
    project.connect()
    project.jira.refuse_summaries = {"Build the overlap check"}

    project.publish(project.approved(STORIES))

    assert len(_notifications(project, "jira_publish_failed")) == 1
    assert _send_emails(project).sent == []
    settings = project.client.get("/api/v1/me/notification-settings").json()
    assert settings["email_on_jira_failure"] is False


def test_saving_settings_without_the_jira_choice_keeps_it(project: Project) -> None:
    project.client.put(
        "/api/v1/me/notification-settings",
        json={"email_on_mention": True, "email_on_reply": False, "email_on_jira_failure": False},
    )

    project.client.put(
        "/api/v1/me/notification-settings", json={"email_on_mention": False, "email_on_reply": True}
    )

    assert project.client.get("/api/v1/me/notification-settings").json() == {
        "email_on_mention": False,
        "email_on_reply": True,
        "email_on_jira_failure": False,
    }


def test_an_automatic_publish_tells_the_approver_who_approved(project: Project) -> None:
    project.connect()
    project.client.patch(
        f"{PROJECT}/jira/connection", json={"auto_publish": True, "expected_revision": 1}
    )

    decision = project.approve(project.draft(STORIES))
    project.publish_until_finished(project.get_publish({"id": decision["jira_publish_id"]}))

    assert _notified_users(project, "jira_published") == {LOCAL_REVIEWER_ID}


def test_approvers_hear_once_that_the_token_expires_within_14_days(project: Project) -> None:
    project.connect(token_expires_on=(utc_now().date() + timedelta(days=10)).isoformat())
    tomorrow = utc_now() + timedelta(days=1, minutes=1)

    project.background_round(tomorrow)
    project.background_round(tomorrow + timedelta(days=1))
    mail = _send_emails(project, tomorrow + timedelta(days=1))

    expiring = _notifications(project, "jira_token_expiring")
    assert len(expiring) == 1
    assert expiring[0]["details"]["days_left"] == 9
    with _session(project.database_url) as session:
        approvers = set(
            session.scalars(
                select(MembershipRecord.user_id).where(
                    MembershipRecord.project_id == DEMO_PROJECT_ID,
                    MembershipRecord.role == Role.APPROVER.value,
                )
            )
        )
    assert _notified_users(project, "jira_token_expiring") == approvers
    assert len(mail.sent) == len(approvers)
    assert all("expires in 9 days" in message.subject for message in mail.sent)


def test_approvers_hear_once_when_jira_stops_accepting_the_token(project: Project) -> None:
    project.connect()
    project.jira.revoked = True
    later = utc_now() + timedelta(days=1, minutes=1)

    project.background_round(later)
    project.background_round(later + timedelta(days=1))
    mail = _send_emails(project, later + timedelta(days=1))

    assert len(_notifications(project, "jira_token_stopped")) == 1
    assert mail.sent
    assert all(m.subject.startswith("Publishing to Jira has stopped in ") for m in mail.sent)
    assert all(TOKEN not in m.text for m in mail.sent)
    assert state_of(project.client.get(f"{PROJECT}/jira/connection").json()["connection"]) == (
        "rejected"
    )
