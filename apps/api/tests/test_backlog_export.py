"""Exporting approved backlog versions as JSON and a Jira CSV, through the API and the database.
The drafts are synthetic and cite a stored synthetic brief."""

import csv
import io
from collections.abc import Generator
from contextlib import contextmanager
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

Json = dict[str, Any]

BRIEF = b"# Room booking\n\nStudents book study rooms one slot at a time."
TRANSCRIPT = b"**Dana:** Rooms open at eight."


@contextmanager
def _session(database_url: str) -> Generator[Session]:
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        yield session
        session.commit()
    engine.dispose()


class Exports:
    """The demo project with a stored brief and transcript, drafts saved as a run saves them, and approvals."""

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
                            evidence=(
                                Evidence(self.brief, self.booking_block, "one slot at a time"),
                            ),
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

    def key(self) -> str:
        self.keys += 1
        return f"export-test-key-{self.keys:04d}"

    def get(self, version_id: object) -> Json:
        response = self.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/backlogs/{version_id}")
        assert response.status_code == 200, response.text
        return response.json()

    def settle(self, draft: Json, suggestion: str) -> Json:
        story = next(item for item in draft["items"] if item["kind"] == "story")
        criteria = [{"id": c["id"], "text": c["text"]} for c in story["criteria"]]
        criteria[1]["suggestion"] = suggestion
        response = self.client.patch(
            f"/api/v1/backlogs/{draft['id']}/items/{story['id']}",
            json={"expected_revision": draft["revision"], "criteria": criteria},
            headers={"Idempotency-Key": self.key()},
        )
        assert response.status_code == 200, response.text
        return response.json()

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
        return response.json()

    def approved(
        self, title: str, baseline: Json | None = None, suggestion: str = "accepted"
    ) -> Json:
        draft = self.settle(self.save_draft(title, base=baseline), suggestion)
        self.approve(draft, baseline)
        return self.get(draft["id"])

    def reject(self, draft: Json) -> None:
        response = self.client.post(
            f"/api/v1/backlogs/{draft['id']}/reject",
            json={"expected_revision": draft["revision"], "reason": "Not this term."},
            headers={"Idempotency-Key": self.key()},
        )
        assert response.status_code == 200, response.text

    def export(self, version: Json | str, export_format: str | None = "json") -> Response:
        version_id = version if isinstance(version, str) else version["id"]
        params = {} if export_format is None else {"format": export_format}
        return self.client.get(f"/api/v1/backlogs/{version_id}/export", params=params)

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
def exports(client: TestClient, seeded_database_url: str) -> Exports:
    return Exports(client, seeded_database_url)


def _error(response: Response, status: int, code: str) -> Json:
    assert (response.status_code, response.json()["code"]) == (status, code), response.text
    body: Json = response.json()
    return body


def _without_export_fields(version: Json) -> Json:
    """The stored version's content in the export's layout, for comparing the two."""
    return {
        "items": [
            {
                key: value
                for key, value in item.items()
                if key not in {"blockers", "edited_by", "edited_at"}
            }
            | {
                "criteria": [
                    {
                        key: value
                        for key, value in criterion.items()
                        if key not in {"suggestion", "edited_by"}
                    }
                    for criterion in item["criteria"]
                ]
            }
            for item in version["items"]
        ],
        "decisions": [
            {key: value for key, value in decision.items() if key != "question_id"}
            for decision in version["decisions"]
        ],
        "out_of_scope": version["out_of_scope"],
    }


def test_json_export_is_the_stored_approved_version_with_its_approval(exports: Exports) -> None:
    version = exports.approved("Book a room", suggestion="rejected")

    response = exports.export(version)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-disposition"] == (
        'attachment; filename="campus-room-booking-backlog-v1.json"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    exported = response.json()
    assert exported["schema_version"] == "scopesteps.backlog-export.v1"
    assert exported["project"] == {"id": str(DEMO_PROJECT_ID), "name": "Campus Room Booking"}
    assert exported["version"] | {"approved_at": None, "created_at": None} == {
        "id": version["id"],
        "number": 1,
        "state": "approved",
        "revision": version["revision"],
        "content_hash": version["content_hash"],
        "base_version_id": None,
        "run_id": version["run_id"],
        "source_version_ids": [str(exports.brief)],
        "created_at": None,
        "approved_by": str(LOCAL_REVIEWER_ID),
        "approved_at": None,
    }
    stored = _without_export_fields(version)
    assert {key: exported[key] for key in stored} == stored
    story = exported["items"][1]
    assert [c["text"] for c in story["criteria"]] == ["A student books one slot."], (
        "the rejected suggestion was left out when the version was frozen"
    )
    assert story["criteria"][0]["evidence"] == [
        {
            "source_version_id": str(exports.brief),
            "block_id": str(exports.booking_block),
            "quote": "one slot at a time",
            "relationship": "supporting",
        }
    ]
    assert story["criteria"][0]["origin"] == "source"
    assert exported["withheld_evidence_count"] == 0


def _csv_rows(response: Response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.content.decode("utf-8"), newline="")))


def test_csv_export_is_the_approved_epics_and_stories_for_jira(exports: Exports) -> None:
    version = exports.approved('Book a room, "now"')

    response = exports.export(version, "csv")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8; header=present"
    assert response.headers["content-disposition"] == (
        'attachment; filename="campus-room-booking-backlog-v1.csv"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert not response.content.startswith(b"\xef\xbb\xbf")
    assert _csv_rows(response) == [
        ["Issue ID", "Issue Type", "Summary", "Description", "Parent"],
        ["1", "Epic", "Room booking", "Booking study rooms.", ""],
        [
            "2",
            "Story",
            'Book a room, "now"',
            "As a student, I want a room, so that I can study.\n\n"
            "Acceptance criteria\n- A student books one slot.\n- The student sees a confirmation.",
            "1",
        ],
    ]


def test_csv_carries_no_evidence_ids_hashes_or_approval(exports: Exports) -> None:
    version = exports.approved("Book a room")

    text = exports.export(version, "csv").text

    story = version["items"][1]
    for value in (
        version["id"],
        version["content_hash"],
        version["run_id"],
        str(exports.brief),
        str(exports.booking_block),
        str(LOCAL_REVIEWER_ID),
        str(DEMO_PROJECT_ID),
        "one slot at a time",
        *(item["id"] for item in version["items"]),
        *(criterion["id"] for criterion in story["criteria"]),
        "supporting",
        "proposed",
    ):
        assert value not in text, value


def test_the_same_approved_version_exports_the_same_csv_bytes(exports: Exports) -> None:
    version = exports.approved("Book a room")

    first, second = exports.export(version, "csv"), exports.export(version, "csv")

    assert first.content == second.content


def test_exporting_v1_after_v2_exists_returns_v1(exports: Exports) -> None:
    v1 = exports.approved("Book a room")
    v2 = exports.approved("Book a study room", baseline=v1)

    first = exports.export(v1).json()
    second = exports.export(v2).json()

    assert (first["version"]["id"], first["version"]["number"]) == (v1["id"], 1)
    assert first["items"][1]["title"] == "Book a room"
    assert (second["version"]["id"], second["version"]["number"]) == (v2["id"], 2)
    assert second["version"]["base_version_id"] == v1["id"]
    assert second["items"][1]["title"] == "Book a study room"
    v1_csv = exports.export(v1, "csv")
    assert v1_csv.headers["content-disposition"].endswith('backlog-v1.csv"')
    assert _csv_rows(v1_csv)[2][2] == "Book a room"


def test_a_later_draft_does_not_change_the_approved_export(exports: Exports) -> None:
    v1 = exports.approved("Book a room")
    before = exports.export(v1).json()
    exports.settle(exports.save_draft("Book any room", base=v1), "rejected")

    after = exports.export(v1).json()

    assert {k: v for k, v in after.items() if k != "exported_at"} == {
        k: v for k, v in before.items() if k != "exported_at"
    }


@pytest.mark.parametrize("export_format", [None, "json"])
def test_json_is_the_default_format(exports: Exports, export_format: str | None) -> None:
    version = exports.approved("Book a room")

    response = exports.export(version, export_format)

    assert response.headers["content-type"] == "application/json"


@pytest.mark.parametrize("export_format", ["markdown", "CSV", "JSON", "pdf", ""])
def test_an_unsupported_format_is_a_validation_error(exports: Exports, export_format: str) -> None:
    version = exports.approved("Book a room")

    response = exports.export(version, export_format)

    body = _error(response, 422, "VALIDATION_ERROR")
    assert body["details"]["errors"][0]["loc"] == ["query", "format"]
    assert "'csv' or 'json'" in body["details"]["errors"][0]["msg"]


@pytest.mark.parametrize("role", [Role.VIEWER, Role.EDITOR, Role.APPROVER])
def test_any_member_may_export_an_approved_version(exports: Exports, role: Role) -> None:
    version = exports.approved("Book a room")
    exports.hold_roles(role)

    for export_format in ("json", "csv"):
        assert exports.export(version, export_format).status_code == 200


def test_a_non_member_gets_not_found_and_no_content(exports: Exports) -> None:
    version = exports.approved("Book a room")
    draft = exports.save_draft("A draft room")
    exports.hold_roles()

    for target in (version, draft):
        for export_format in ("json", "csv"):
            response = exports.export(target, export_format)

            body = _error(response, 404, "NOT_FOUND")
            assert "Book a room" not in response.text
            assert body["details"] == {}


def test_an_unknown_version_is_not_found(exports: Exports) -> None:
    _error(exports.export(str(new_id())), 404, "NOT_FOUND")


def test_a_draft_cannot_be_exported(exports: Exports) -> None:
    draft = exports.save_draft("A draft room")

    for export_format in ("json", "csv"):
        response = exports.export(draft, export_format)

        body = _error(response, 409, "VERSION_NOT_APPROVED")
        assert body["details"] == {"state": "draft"}
        assert "A draft room" not in response.text


def test_a_rejected_version_cannot_be_exported(exports: Exports) -> None:
    draft = exports.save_draft("A rejected room")
    exports.reject(draft)

    for export_format in ("json", "csv"):
        response = exports.export(draft, export_format)

        assert _error(response, 409, "VERSION_NOT_APPROVED")["details"] == {"state": "rejected"}
