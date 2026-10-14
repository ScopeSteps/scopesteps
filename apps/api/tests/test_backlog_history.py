"""Listing a project's backlog versions and comparing two of them, through the API and the
database. The drafts are synthetic and cite a stored synthetic brief."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import delete
from sqlalchemy.orm import Session

from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID
from scopesteps.backlog.client import (
    BacklogVersionId,
    CandidateProposal,
    Evidence,
    ProposedCriterion,
    ProposedItem,
    save_candidate,
)
from scopesteps.backlog.domain.version import VersionState
from scopesteps.backlog.infrastructure.orm import VersionRecord
from scopesteps.backlog.infrastructure.repository import SqlVersionRepository
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

Json = dict[str, Any]

BRIEF = b"# Room booking\n\nStudents book study rooms one slot at a time."
TRANSCRIPT = b"**Dana:** Rooms open at eight."
LIST_URL = f"/api/v1/projects/{DEMO_PROJECT_ID}/backlogs"


@contextmanager
def _session(database_url: str) -> Generator[Session]:
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        yield session
        session.commit()
    engine.dispose()


class History:
    """The demo project with stored sources, drafts saved as a run saves them, and decisions."""

    def __init__(self, client: TestClient, database_url: str) -> None:
        self.client = client
        self.database_url = database_url
        self.keys = 0
        response = client.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/sources",
            files={"brief": ("brief.md", BRIEF), "transcript": ("transcript.md", TRANSCRIPT)},
            headers={"Idempotency-Key": "upload-key-0001"},
        )
        assert response.status_code == 201, response.text
        self.brief = UUID(response.json()["source_versions"][0]["id"])
        url = f"/api/v1/projects/{DEMO_PROJECT_ID}/sources/{self.brief}/blocks"
        self.booking_block = UUID(self.client.get(url).json()[1]["id"])

    def save_draft(self, title: str, base: Json | None = None) -> Json:
        """A draft with a cited criterion and an agent suggestion still to review."""
        proposal = CandidateProposal(
            project_id=DEMO_PROJECT_ID,
            run_id=new_id(),
            created_by=LOCAL_REVIEWER_ID,
            source_version_ids=(self.brief,),
            items=(
                ProposedItem("E1", "epic", None, "Room booking", "Booking study rooms."),
                ProposedItem(
                    "S1",
                    "story",
                    "E1",
                    title,
                    "As a student, I want a room, so that I can study.",
                    criteria=(
                        ProposedCriterion(
                            "A student books one slot.",
                            proposed=False,
                            evidence=(Evidence(self.brief, self.booking_block),),
                        ),
                        ProposedCriterion("The student sees a confirmation.", proposed=True),
                    ),
                ),
            ),
        )
        with _session(self.database_url) as session:
            version_id = save_candidate(session, proposal, utc_now())
            if base is not None:
                record = session.get_one(VersionRecord, version_id)
                record.base_version_id = BacklogVersionId(UUID(base["id"]))
        return self.get(version_id)

    def save_change_draft(self, base: Json) -> Json:
        """A draft that keeps the base version's ids, as a change to it would."""
        with _session(self.database_url) as session:
            versions = SqlVersionRepository(session)
            stored = versions.get(BacklogVersionId(UUID(base["id"])))
            assert stored is not None
            draft = replace(
                stored,
                id=BacklogVersionId(new_id()),
                base_version_id=stored.id,
                state=VersionState.DRAFT,
                revision=1,
                run_id=None,
                created_at=utc_now(),
            )
            versions.add(draft)
        return self.get(draft.id)

    def key(self) -> str:
        self.keys += 1
        return f"history-test-key-{self.keys:04d}"

    def get(self, version_id: object) -> Json:
        response = self.client.get(f"{LIST_URL}/{version_id}")
        assert response.status_code == 200, response.text
        return response.json()

    def patch_story(self, draft: Json, **body: Any) -> Json:
        story = _story(draft)
        response = self.client.patch(
            f"/api/v1/backlogs/{draft['id']}/items/{story['id']}",
            json={"expected_revision": draft["revision"], **body},
            headers={"Idempotency-Key": self.key()},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def accept_suggestion(self, draft: Json) -> Json:
        criteria = [{"id": c["id"], "text": c["text"]} for c in _story(draft)["criteria"]]
        criteria[1]["suggestion"] = "accepted"
        return self.patch_story(draft, criteria=criteria)

    def approve(self, draft: Json, baseline: Json | None = None) -> Json:
        response = self.client.post(
            f"/api/v1/backlogs/{draft['id']}/approve",
            json={
                "expected_revision": draft["revision"],
                "content_hash": draft["content_hash"],
                "expected_baseline_id": None if baseline is None else baseline["id"],
            },
            headers={"Idempotency-Key": self.key()},
        )
        assert response.status_code == 200, response.text
        return self.get(draft["id"])

    def reject(self, draft: Json) -> Json:
        response = self.client.post(
            f"/api/v1/backlogs/{draft['id']}/reject",
            json={"expected_revision": draft["revision"], "reason": "Not this term."},
            headers={"Idempotency-Key": self.key()},
        )
        assert response.status_code == 200, response.text
        return self.get(draft["id"])

    def list(self, **params: Any) -> Response:
        return self.client.get(LIST_URL, params=params)

    def compare(self, base: Json | str, candidate: Json | str) -> Response:
        return self.client.get(
            f"{LIST_URL}/compare",
            params={"base": _id(base), "candidate": _id(candidate)},
        )

    def hold_roles(self, *roles: Role) -> None:
        """Leave the local reviewer with exactly `roles` in the demo project."""
        with _session(self.database_url) as session:
            session.execute(
                delete(MembershipRecord).where(
                    MembershipRecord.user_id == LOCAL_REVIEWER_ID,
                    MembershipRecord.project_id == DEMO_PROJECT_ID,
                )
            )
            grant_project_roles(
                SqlUserRepository(session),
                LOCAL_REVIEWER_ID,
                ProjectId(DEMO_PROJECT_ID),
                roles,
                utc_now(),
            )


@pytest.fixture
def history(client: TestClient, seeded_database_url: str) -> History:
    return History(client, seeded_database_url)


def _id(version: Json | str) -> str:
    return version if isinstance(version, str) else str(version["id"])


def _story(version: Json) -> Json:
    return next(item for item in version["items"] if item["kind"] == "story")


def _error(response: Response, status: int, code: str) -> Json:
    assert (response.status_code, response.json()["code"]) == (status, code), response.text
    body: Json = response.json()
    return body


def _versions(response: Response) -> list[Json]:
    assert response.status_code == 200, response.text
    versions: list[Json] = response.json()["versions"]
    return versions


def test_an_empty_project_lists_no_versions(client: TestClient) -> None:
    response = client.get(LIST_URL)

    assert response.status_code == 200, response.text
    assert response.json() == {"versions": [], "next_cursor": None}


def test_a_draft_is_listed_without_a_number_or_decision(history: History) -> None:
    draft = history.save_draft("Book a room")

    (listed,) = _versions(history.list())

    assert listed == {
        "id": draft["id"],
        "number": None,
        "state": "draft",
        "revision": 1,
        "content_hash": draft["content_hash"],
        "base_version_id": None,
        "run_id": draft["run_id"],
        "created_by": str(LOCAL_REVIEWER_ID),
        "created_at": draft["created_at"],
        "decision": None,
    }


def test_approved_and_rejected_versions_are_listed_newest_first(history: History) -> None:
    v1 = history.approve(history.accept_suggestion(history.save_draft("Book a room")))
    v2 = history.approve(
        history.accept_suggestion(history.save_draft("Book a study room", base=v1)), v1
    )
    rejected = history.reject(history.save_draft("Book any room", base=v2))

    listed = _versions(history.list())

    assert [(v["id"], v["state"], v["number"]) for v in listed] == [
        (rejected["id"], "rejected", None),
        (v2["id"], "approved", 2),
        (v1["id"], "approved", 1),
    ]
    assert [v["base_version_id"] for v in listed] == [v2["id"], v1["id"], None]
    assert [v["revision"] for v in listed] == [1, 2, 2]
    assert [v["content_hash"] for v in listed] == [
        rejected["content_hash"],
        v2["content_hash"],
        v1["content_hash"],
    ]
    for version in listed:
        decision = version["decision"]
        assert decision["decided_by"] == str(LOCAL_REVIEWER_ID)
        assert decision["decided_at"] is not None
    assert [v["decision"]["decision"] for v in listed] == ["rejected", "approved", "approved"]


def test_the_list_is_paged_by_cursor(history: History) -> None:
    drafts = [history.save_draft(f"Story {n}") for n in range(3)]

    first = history.list(limit=2).json()
    second = history.list(limit=2, cursor=first["next_cursor"]).json()

    assert [v["id"] for v in first["versions"]] == [drafts[2]["id"], drafts[1]["id"]]
    assert [v["id"] for v in second["versions"]] == [drafts[0]["id"]]
    assert second["next_cursor"] is None


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"cursor": "not-a-cursor"}, "INVALID_CURSOR"),
        ({"limit": 0}, "VALIDATION_ERROR"),
        ({"limit": 101}, "VALIDATION_ERROR"),
    ],
)
def test_an_invalid_page_request_is_refused(history: History, params: Json, code: str) -> None:
    _error(history.list(**params), 422, code)


def test_comparing_v1_and_v2_reports_changes_by_stable_id(history: History) -> None:
    v1 = history.approve(history.accept_suggestion(history.save_draft("Book a room")))
    draft = history.save_change_draft(v1)
    criteria = [{"id": c["id"], "text": c["text"]} for c in _story(draft)["criteria"]]
    criteria[0]["text"] = "A signed-in student books one slot."
    criteria.append({"text": "Rooms show their capacity."})
    v2 = history.approve(
        history.patch_story(draft, title="Book a study room", criteria=criteria), v1
    )

    response = history.compare(v1, v2)

    assert response.status_code == 200, response.text
    comparison = response.json()
    assert (comparison["base_version_id"], comparison["candidate_version_id"]) == (
        v1["id"],
        v2["id"],
    )
    assert (comparison["base_content_hash"], comparison["candidate_content_hash"]) == (
        v1["content_hash"],
        v2["content_hash"],
    )
    v1_story = _story(v1)
    (operation,) = comparison["operations"]
    assert (operation["kind"], operation["item_id"], operation["changed_fields"]) == (
        "modify_item",
        v1_story["id"],
        ["title"],
    )
    assert (operation["before"]["title"], operation["after"]["title"]) == (
        "Book a room",
        "Book a study room",
    )
    assert [(c["kind"], c["criterion_id"]) for c in operation["criteria"]] == [
        ("modified", v1_story["criteria"][0]["id"]),
        ("added", _story(v2)["criteria"][2]["id"]),
    ]
    assert operation["criteria"][0]["after"]["text"] == "A signed-in student books one slot."
    backwards = history.compare(v2, v1).json()["operations"][0]["criteria"]
    assert [c["kind"] for c in backwards] == ["modified", "removed"]


def test_versions_with_their_own_ids_compare_as_added_and_removed(history: History) -> None:
    v1 = history.approve(history.accept_suggestion(history.save_draft("Book a room")))
    draft = history.save_draft("Book a room", base=v1)

    operations = history.compare(v1, draft).json()["operations"]

    assert sorted(o["kind"] for o in operations) == ["add_item"] * 2 + ["remove_item"] * 2
    assert {o["item_id"] for o in operations if o["kind"] == "remove_item"} == {
        i["id"] for i in v1["items"]
    }


def test_comparing_a_version_with_itself_reports_nothing(history: History) -> None:
    draft = history.save_draft("Book a room")

    assert history.compare(draft, draft).json()["operations"] == []


def test_list_and_compare_change_nothing(history: History) -> None:
    v1 = history.approve(history.accept_suggestion(history.save_draft("Book a room")))
    before = history.get(v1["id"])
    activity = history.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/activity").json()

    history.list()
    history.compare(v1, v1)

    assert history.get(v1["id"]) == before
    assert history.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/activity").json() == activity
    assert history.client.post(LIST_URL, json={}).status_code == 405


@pytest.mark.parametrize("role", [Role.VIEWER, Role.EDITOR, Role.APPROVER])
def test_any_member_may_list_and_compare(history: History, role: Role) -> None:
    draft = history.save_draft("Book a room")
    history.hold_roles(role)

    assert history.list().status_code == 200
    assert history.compare(draft, draft).status_code == 200


def test_a_non_member_gets_not_found(history: History) -> None:
    draft = history.save_draft("Book a room")
    history.hold_roles()

    _error(history.list(), 404, "NOT_FOUND")
    response = history.compare(draft, draft)
    _error(response, 404, "NOT_FOUND")
    assert "Book a room" not in response.text


def test_a_version_of_another_project_is_not_found(history: History) -> None:
    draft = history.save_draft("Book a room")
    created = history.client.post(
        "/api/v1/projects",
        json={"name": "Library loans"},
        headers={"Idempotency-Key": "project-key-0001"},
    )
    assert created.status_code == 201, created.text
    other = created.json()["id"]

    response = history.client.get(
        f"/api/v1/projects/{other}/backlogs/compare",
        params={"base": draft["id"], "candidate": draft["id"]},
    )

    _error(response, 404, "NOT_FOUND")
    assert history.client.get(f"/api/v1/projects/{other}/backlogs").json()["versions"] == []


def test_an_unknown_version_is_not_found(history: History) -> None:
    draft = history.save_draft("Book a room")

    _error(history.compare(draft, str(new_id())), 404, "NOT_FOUND")
    _error(history.compare(draft, "not-a-uuid"), 422, "VALIDATION_ERROR")
