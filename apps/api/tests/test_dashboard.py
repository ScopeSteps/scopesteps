"""The project dashboard: every figure matches the page it comes from, waits come from stored
times, members only, and a large backlog answers quickly."""

import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from scopesteps.agent.domain.run import QuestionStatus, RunStage, RunStatus
from scopesteps.agent.infrastructure.orm import QuestionRecord, RunRecord
from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID
from scopesteps.audit.client import ActorKind, EventType, SubjectKind
from scopesteps.audit.infrastructure.orm import AuditEventRecord
from scopesteps.backlog.client import (
    BacklogVersionId,
    CandidateProposal,
    Evidence,
    ProposedCriterion,
    ProposedItem,
    save_candidate,
)
from scopesteps.backlog.infrastructure.orm import VersionRecord
from scopesteps.change_control.client import ChangeRequestStatus
from scopesteps.change_control.infrastructure.orm import ApprovalRecord, ChangeRequestRecord
from scopesteps.identity.infrastructure.orm import MembershipRecord
from scopesteps.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    utc_now,
)
from scopesteps.kernel.ids import new_id

Json = dict[str, Any]

PROJECT = f"/api/v1/projects/{DEMO_PROJECT_ID}"
DASHBOARD = f"{PROJECT}/dashboard"
# Fixed times far enough in the past that every wait below is positive whatever today is.
T0 = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


@contextmanager
def _session(database_url: str) -> Generator[Session]:
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        yield session
        session.commit()
    engine.dispose()


class Project:
    """The demo project, with versions approved the way an approver approves them."""

    def __init__(self, client: TestClient, database_url: str) -> None:
        self.client = client
        self.database_url = database_url
        self.keys = 0
        uploaded = client.post(
            f"{PROJECT}/sources",
            files={"brief": ("brief.md", b"# Rooms\n\nStudents book study rooms.")},
            headers={"Idempotency-Key": "dashboard-upload-0001"},
        )
        assert uploaded.status_code == 201, uploaded.text
        self.brief = UUID(uploaded.json()["source_versions"][0]["id"])
        blocks = client.get(f"{PROJECT}/sources/{self.brief}/blocks").json()
        self.block = UUID(blocks[1]["id"])

    def key(self) -> str:
        self.keys += 1
        return f"dashboard-key-{self.keys:04d}"

    def approved(self, stories: dict[str, list[str]], base: Json | None = None) -> Json:
        """A draft of one epic with `stories` (title: its tasks), approved as the next version."""
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
        draft = self.client.get(f"{PROJECT}/backlogs/{version_id}").json()
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
        response = self.client.post(
            f"/api/v1/backlogs/{draft['id']}/approve",
            json={
                "expected_revision": draft["revision"],
                "content_hash": draft["content_hash"],
                "expected_baseline_id": None if base is None else base["id"],
            },
            headers={"Idempotency-Key": self.key()},
        )
        assert response.status_code == 200, response.text
        return self.client.get(f"{PROJECT}/backlogs/{draft['id']}").json()

    def decided_at(self, version: Json, when: datetime) -> None:
        with _session(self.database_url) as session:
            session.execute(
                update(ApprovalRecord)
                .where(ApprovalRecord.version_id == UUID(version["id"]))
                .values(decided_at=when)
            )

    def change_request(
        self,
        status: ChangeRequestStatus,
        requested_at: datetime,
        candidate: Json | None = None,
        *,
        base: Json,
    ) -> None:
        with _session(self.database_url) as session:
            number = 1 + session.query(ChangeRequestRecord).count()
            session.add(
                ChangeRequestRecord(
                    id=new_id(),
                    project_id=DEMO_PROJECT_ID,
                    number=number,
                    text="Allow bookings of up to three hours.",
                    requested_by=LOCAL_REVIEWER_ID,
                    requested_by_name="Local Reviewer",
                    requested_at=requested_at,
                    base_version_id=UUID(base["id"]),
                    base_content_hash="0" * 64,
                    source_version_id=self.brief,
                    run_id=new_id(),
                    status=status,
                    revision=1,
                    candidate_version_id=None if candidate is None else UUID(candidate["id"]),
                    change_set={},
                )
            )

    def questions_asked_at(self, asked: list[datetime]) -> None:
        """A run waiting on one open question per time, each logged as the agent asks it."""
        run_id = new_id()
        with _session(self.database_url) as session:
            session.add(
                RunRecord(
                    id=run_id,
                    project_id=DEMO_PROJECT_ID,
                    mode="initial",
                    status=RunStatus.WAITING_FOR_INPUT,
                    stage=RunStage.EXPLORE,
                    revision=1,
                    inputs={"source_version_ids": []},
                    model_turns=1,
                    tool_calls=0,
                    total_tokens=0,
                    input_tokens=0,
                    output_tokens=0,
                    thinking_tokens=0,
                    cost_microusd=0,
                    clarification_rounds=1,
                    history=[],
                    pending_results=[],
                    draft=None,
                    problems=[],
                    created_by=LOCAL_REVIEWER_ID,
                    created_at=T0,
                    updated_at=T0,
                )
            )
            session.flush()
            for number, when in enumerate(asked):
                question_id = new_id()
                session.add(
                    QuestionRecord(
                        id=question_id,
                        run_id=run_id,
                        round=1,
                        call_id=f"call-{number}",
                        subject=f"Booking length {number}",
                        text="How long may a booking last?",
                        why_it_matters="Sources disagree.",
                        block_labels=[],
                        status=QuestionStatus.OPEN,
                    )
                )
                session.add(
                    AuditEventRecord(
                        id=new_id(),
                        project_id=DEMO_PROJECT_ID,
                        actor_kind=ActorKind.AGENT,
                        actor_user_id=None,
                        actor_name=None,
                        type=EventType.CLARIFICATION_REQUESTED,
                        subjects=[
                            {"kind": SubjectKind.RUN.value, "id": str(run_id)},
                            {"kind": SubjectKind.QUESTION.value, "id": str(question_id)},
                        ],
                        summary="Asked 1 clarification question (round 1)",
                        occurred_at=when,
                    )
                )

    def dashboard(self) -> Json:
        response = self.client.get(DASHBOARD)
        assert response.status_code == 200, response.text
        body: Json = response.json()
        return body


@pytest.fixture
def project(
    client: TestClient,
    seeded_database_url: str,
    confirm_speakers: Callable[[TestClient], None],
) -> Project:
    made = Project(client, seeded_database_url)
    confirm_speakers(client)
    return made


def test_a_new_project_says_nothing_is_uploaded_and_has_no_figures(client: TestClient) -> None:
    body = client.get(DASHBOARD).json()

    assert body["has_sources"] is False
    assert (body["counts"], body["coverage"], body["timeline"]) == (None, None, [])
    assert body["open_questions"] == {"count": 0, "oldest": []}
    assert body["change_requests"]["total"] == 0
    assert body["change_requests"]["average_seconds_to_decision"] is None


def test_every_figure_matches_the_page_it_comes_from(project: Project) -> None:
    v1 = project.approved({"Search rooms": ["Build the search form"], "Book a slot": []})
    v2 = project.approved(
        {"Search rooms": ["Build the search form", "Add filters"], "Cancel a booking": []}, v1
    )
    project.decided_at(v1, T0)
    project.decided_at(v2, T0 + timedelta(days=3))
    project.change_request(ChangeRequestStatus.APPROVED, T0 + timedelta(days=1), v2, base=v1)
    project.change_request(ChangeRequestStatus.IN_REVIEW, T0 + timedelta(days=4), base=v2)
    project.change_request(ChangeRequestStatus.FAILED, T0 + timedelta(days=5), base=v2)
    project.questions_asked_at([T0 + timedelta(days=6), T0 + timedelta(days=2)])

    body = project.dashboard()

    # The approved version and its counts, as the Backlog shows v2.
    shown = project.client.get(f"{PROJECT}/backlogs/{v2['id']}").json()
    stories = [item for item in shown["items"] if item["kind"] == "story"]
    assert body["status"]["baseline_version"] == 2
    assert body["counts"] == {
        "version_id": v2["id"],
        "approved": True,
        "epics": sum(item["kind"] == "epic" for item in shown["items"]),
        "stories": len(stories),
        "tasks": sum(len(story["tasks"]) for story in stories),
    }
    assert (body["counts"]["stories"], body["counts"]["tasks"]) == (2, 2)
    # The timeline, as the version history lists the approved versions.
    history = project.client.get(f"{PROJECT}/backlogs").json()["versions"]
    approved = sorted((v for v in history if v["number"]), key=lambda v: v["number"])
    assert [(e["version_id"], e["number"], e["approved_by"]) for e in body["timeline"]] == [
        (v["id"], v["number"], v["decision"]["decided_by"]) for v in approved
    ]
    assert [e["approved_at"] for e in body["timeline"]] == [
        "2026-01-05T09:00:00Z",
        "2026-01-08T09:00:00Z",
    ]
    assert [e["change_request_number"] for e in body["timeline"]] == [None, 1]
    assert body["timeline"][0]["approved_by_name"] == "Local Reviewer"
    # Change requests, as their page lists them; the one decided took two days.
    listed = project.client.get(f"{PROJECT}/change-requests").json()["change_requests"]
    by_status = {row["status"]: row["count"] for row in body["change_requests"]["by_status"]}
    assert by_status == {
        status.value: sum(r["status"] == status.value for r in listed)
        for status in ChangeRequestStatus
    }
    assert body["change_requests"]["total"] == len(listed) == 3
    assert body["change_requests"]["decided"] == 1
    assert body["change_requests"]["average_seconds_to_decision"] == 2 * 86400
    # Open questions, longest waiting first, timed from the activity log.
    oldest = body["open_questions"]["oldest"]
    assert body["open_questions"]["count"] == 2
    assert [q["subject"] for q in oldest] == ["Booking length 1", "Booking length 0"]
    assert oldest[0]["asked_at"] == "2026-01-07T09:00:00Z"
    assert oldest[0]["waited_seconds"] >= (utc_now() - (T0 + timedelta(days=2))).total_seconds() - 5
    # Who things wait on, as the Team page counts it.
    members = project.client.get(f"{PROJECT}/members").json()["members"]
    expected = sorted(
        ((m["display_name"], m["waiting"]) for m in members if m["waiting"] > 0),
        key=lambda pair: (-pair[1], pair[0].casefold()),
    )
    assert [(w["display_name"], w["waiting"]) for w in body["waiting_on"]] == expected
    assert expected, "the change request in review and the open questions wait on someone"


def test_someone_who_is_not_a_member_gets_not_found(
    client: TestClient, seeded_database_url: str
) -> None:
    with _session(seeded_database_url) as session:
        session.execute(
            delete(MembershipRecord).where(
                MembershipRecord.project_id == DEMO_PROJECT_ID,
                MembershipRecord.user_id == LOCAL_REVIEWER_ID,
            )
        )

    response = client.get(DASHBOARD)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_a_large_backlog_answers_within_a_second(project: Project) -> None:
    project.approved({f"Story {n}": [f"Task {n}"] for n in range(200)})

    started = time.perf_counter()
    body = project.dashboard()
    elapsed = time.perf_counter() - started

    assert (body["counts"]["stories"], body["counts"]["tasks"]) == (200, 200)
    assert elapsed < 1.0
