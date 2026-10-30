"""The home page's summary of what waits for the actor on each of their projects, through the API
and the database. Projects, sources, drafts, runs and change requests are synthetic."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, delete, event, select
from sqlalchemy.orm import Session

from scopesteps.agent.domain.run import QuestionStatus, RunStage, RunStatus
from scopesteps.agent.infrastructure.orm import QuestionRecord, RunRecord
from scopesteps.api.seed import LOCAL_REVIEWER_ID, seed
from scopesteps.audit.infrastructure.orm import AuditEventRecord
from scopesteps.backlog.client import (
    CandidateProposal,
    Evidence,
    ProposedCriterion,
    ProposedItem,
    save_candidate,
)
from scopesteps.change_control.client import ChangeRequestStatus
from scopesteps.change_control.infrastructure.orm import ChangeRequestRecord
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

ClientFactory = Callable[..., TestClient]
Json = dict[str, Any]

MY_WORK = "/api/v1/me/work"
BRIEF = b"# Room booking\n\nStudents book study rooms one slot at a time."
TRANSCRIPT = b"**Dana:** A booking lasts at most four hours.\n\n**Lee:** I said three hours."


@contextmanager
def _session(database_url: str) -> Generator[Session]:
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        yield session
        session.commit()
    engine.dispose()


class Workspace:
    """Projects the local reviewer holds chosen roles on, filled with work through the API or,
    where only an agent run could make it, with rows as the run would store them."""

    def __init__(self, client: TestClient, database_url: str) -> None:
        self.client = client
        self.database_url = database_url
        self.keys = 0

    def key(self) -> str:
        self.keys += 1
        return f"my-work-test-key-{self.keys:04d}"

    def project(self, name: str, *roles: Role) -> str:
        """A new project where the reviewer holds exactly `roles`; none leaves them outside it."""
        response = self.client.post(
            "/api/v1/projects", json={"name": name}, headers={"Idempotency-Key": self.key()}
        )
        assert response.status_code == 201, response.text
        project_id: str = response.json()["id"]
        self.with_roles(project_id, *roles)
        return project_id

    def with_roles(self, project_id: str, *roles: Role) -> None:
        with _session(self.database_url) as session:
            session.execute(
                delete(MembershipRecord).where(MembershipRecord.project_id == UUID(project_id))
            )
            if roles:
                grant_project_roles(
                    SqlUserRepository(session),
                    LOCAL_REVIEWER_ID,
                    ProjectId(UUID(project_id)),
                    roles,
                    utc_now(),
                )

    def furnish(self, project_id: str) -> tuple[UUID, UUID]:
        """Two unconfirmed speakers, a draft with one blocker, a run waiting on two questions and
        a change request in review. Leaves the reviewer editor and approver; returns the draft's
        id and the transcript's version id."""
        self.with_roles(project_id, Role.EDITOR, Role.APPROVER)
        response = self.client.post(
            f"/api/v1/projects/{project_id}/sources",
            files={"brief": ("brief.md", BRIEF), "transcript": ("transcript.md", TRANSCRIPT)},
            headers={"Idempotency-Key": self.key()},
        )
        assert response.status_code == 201, response.text
        brief, transcript = (UUID(v["id"]) for v in response.json()["source_versions"])
        block = self.client.get(f"/api/v1/projects/{project_id}/sources/{brief}/blocks").json()[1]
        draft_id = self.save_draft(project_id, brief, transcript, UUID(block["id"]))
        self.waiting_run(project_id, open_questions=2)
        self.change_request(project_id, draft_id, transcript, ChangeRequestStatus.IN_REVIEW)
        return draft_id, transcript

    def save_draft(self, project_id: str, brief: UUID, transcript: UUID, block: UUID) -> UUID:
        """A draft whose only blocker is one agent suggestion nobody has reviewed."""
        proposal = CandidateProposal(
            project_id=ProjectId(UUID(project_id)),
            run_id=new_id(),
            created_by=LOCAL_REVIEWER_ID,
            source_version_ids=(brief, transcript),
            items=(
                ProposedItem("E1", "epic", None, "Room booking", "Booking study rooms."),
                ProposedItem(
                    "S1",
                    "story",
                    "E1",
                    "Book a room",
                    "As a student, I want to book a room, so that I can study.",
                    criteria=(
                        ProposedCriterion(
                            "A student books one slot.",
                            proposed=False,
                            evidence=(Evidence(brief, block),),
                        ),
                        ProposedCriterion("The student sees a confirmation.", proposed=True),
                    ),
                ),
            ),
            decisions=(),
        )
        with _session(self.database_url) as session:
            return save_candidate(session, proposal, utc_now())

    def waiting_run(
        self,
        project_id: str,
        *,
        open_questions: int,
        answered: int = 1,
        status: RunStatus = RunStatus.WAITING_FOR_INPUT,
    ) -> None:
        now = utc_now()
        run_id = new_id()
        with _session(self.database_url) as session:
            session.add(
                RunRecord(
                    id=run_id,
                    project_id=UUID(project_id),
                    mode="draft",
                    status=status,
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
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            statuses = [QuestionStatus.OPEN] * open_questions + [QuestionStatus.ANSWERED] * answered
            for number, question_status in enumerate(statuses):
                session.add(
                    QuestionRecord(
                        id=new_id(),
                        run_id=run_id,
                        round=1,
                        call_id=f"call-{number}",
                        subject=f"Question {number}",
                        text="How long may a booking last?",
                        why_it_matters="Sources disagree.",
                        block_labels=[],
                        status=question_status,
                    )
                )

    def change_request(
        self, project_id: str, base_id: UUID, source_version_id: UUID, status: ChangeRequestStatus
    ) -> None:
        with _session(self.database_url) as session:
            number = 1 + len(
                session.scalars(
                    select(ChangeRequestRecord.id).where(
                        ChangeRequestRecord.project_id == UUID(project_id)
                    )
                ).all()
            )
            session.add(
                ChangeRequestRecord(
                    id=new_id(),
                    project_id=UUID(project_id),
                    number=number,
                    text="Allow bookings of up to three hours.",
                    requested_by=LOCAL_REVIEWER_ID,
                    requested_by_name="Local Reviewer",
                    requested_at=utc_now(),
                    base_version_id=base_id,
                    base_content_hash="0" * 64,
                    source_version_id=source_version_id,
                    run_id=new_id(),
                    status=status,
                    revision=1,
                    change_set={},
                )
            )

    def my_work(self) -> Json:
        response = self.client.get(MY_WORK)
        assert response.status_code == 200, response.text
        body: Json = response.json()
        return body

    def entry(self, project_id: str) -> Json:
        return next(p for p in self.my_work()["projects"] if p["id"] == project_id)


@pytest.fixture
def workspace(migrated_database_url: str, make_client: ClientFactory) -> Workspace:
    engine = create_database_engine(migrated_database_url)
    with create_session_factory(engine)() as session:
        seed(session)
    engine.dispose()
    workspace_ = Workspace(make_client(migrated_database_url), migrated_database_url)
    # The seeded demo project is not part of these scenarios.
    with _session(migrated_database_url) as session:
        session.execute(
            delete(MembershipRecord).where(MembershipRecord.user_id == LOCAL_REVIEWER_ID)
        )
    return workspace_


def test_each_project_carries_only_the_counts_the_actors_roles_there_allow(
    workspace: Workspace,
) -> None:
    approving = workspace.project("Library app")
    editing = workspace.project("Lab bookings")
    viewing = workspace.project("Sports hall")
    for project_id in (approving, editing, viewing):
        workspace.furnish(project_id)
    workspace.with_roles(approving, Role.APPROVER)
    workspace.with_roles(editing, Role.EDITOR)
    workspace.with_roles(viewing, Role.VIEWER)

    found = {p["id"]: p for p in workspace.my_work()["projects"]}

    assert found[approving]["roles"] == ["approver"]
    assert found[approving]["approver"] == {
        "change_requests_in_review": 1,
        "draft_ready_for_approval": False,
    }
    assert found[approving]["editor"] is None
    assert found[editing]["roles"] == ["editor"]
    assert found[editing]["approver"] is None
    assert found[editing]["editor"] == {
        "open_questions": 2,
        "draft_blockers": 1,
        "unconfirmed_speakers": 2,
    }
    assert found[viewing]["roles"] == ["viewer"]
    assert found[viewing]["approver"] is None
    assert found[viewing]["editor"] is None
    assert found[viewing]["waiting"] == 0
    assert all(p["recent_activity"]["events"] >= 1 for p in found.values())


def test_the_summary_totals_projects_and_waiting_work_per_role(workspace: Workspace) -> None:
    approving = workspace.project("Library app")
    both = workspace.project("Lab bookings")
    viewing = workspace.project("Sports hall")
    for project_id in (approving, both, viewing):
        workspace.furnish(project_id)
    workspace.with_roles(approving, Role.APPROVER)
    workspace.with_roles(both, Role.EDITOR, Role.APPROVER)
    workspace.with_roles(viewing, Role.VIEWER)

    body = workspace.my_work()

    assert body["roles"] == [
        {"role": "approver", "projects": 2, "waiting": 2},
        {"role": "editor", "projects": 1, "waiting": 5},
        {"role": "viewer", "projects": 1, "waiting": 0},
    ]
    assert body["activity_window_days"] == 7
    assert [p["id"] for p in body["projects"]] == [both, approving, viewing]
    assert [p["waiting"] for p in body["projects"]] == [6, 1, 0]


def test_each_count_matches_what_the_project_pages_show(workspace: Workspace) -> None:
    project_id = workspace.project("Library app")
    workspace.furnish(project_id)
    base = f"/api/v1/projects/{project_id}"

    entry = workspace.entry(project_id)

    status = workspace.client.get(base).json()["status"]
    draft = workspace.client.get(f"{base}/backlogs/{status['open_version_id']}").json()
    people = workspace.client.get(f"{base}/people").json()
    requests = workspace.client.get(f"{base}/change-requests").json()["change_requests"]
    assert entry["status"] == status
    assert entry["editor"]["draft_blockers"] == len(draft["blockers"])
    assert entry["editor"]["unconfirmed_speakers"] == len(people["unconfirmed_speakers"])
    assert entry["approver"]["change_requests_in_review"] == sum(
        r["status"] == "in_review" for r in requests
    )
    assert entry["editor"]["open_questions"] == 2


def test_only_open_questions_in_runs_waiting_for_input_count(workspace: Workspace) -> None:
    project_id = workspace.project("Library app", Role.EDITOR)
    workspace.waiting_run(project_id, open_questions=1, answered=2)
    workspace.waiting_run(project_id, open_questions=3, status=RunStatus.CANCELLED)

    assert workspace.entry(project_id)["editor"]["open_questions"] == 1


def test_only_change_requests_in_review_count(workspace: Workspace) -> None:
    project_id = workspace.project("Library app")
    draft_id, transcript = workspace.furnish(project_id)
    for other in (ChangeRequestStatus.APPROVED, ChangeRequestStatus.ANALYZING):
        workspace.change_request(project_id, draft_id, transcript, other)

    assert workspace.entry(project_id)["approver"]["change_requests_in_review"] == 1


def test_a_draft_with_nothing_blocking_it_is_ready_for_the_approver(workspace: Workspace) -> None:
    project_id = workspace.project("Library app")
    workspace.furnish(project_id)
    base = f"/api/v1/projects/{project_id}"
    draft = workspace.client.get(
        f"{base}/backlogs/{workspace.client.get(base).json()['status']['open_version_id']}"
    ).json()
    story = next(item for item in draft["items"] if item["kind"] == "story")
    criteria = [{"id": c["id"], "text": c["text"]} for c in story["criteria"]]
    criteria[1]["suggestion"] = "accepted"
    response = workspace.client.patch(
        f"/api/v1/backlogs/{draft['id']}/items/{story['id']}",
        json={"expected_revision": draft["revision"], "criteria": criteria},
        headers={"Idempotency-Key": workspace.key()},
    )
    assert response.status_code == 200, response.text

    entry = workspace.entry(project_id)

    assert entry["approver"]["draft_ready_for_approval"] is True
    assert entry["editor"]["draft_blockers"] == 0


def test_recent_activity_looks_back_seven_days(workspace: Workspace) -> None:
    project_id = workspace.project("Library app")
    workspace.furnish(project_id)

    activity = workspace.entry(project_id)["recent_activity"]

    assert activity["events"] >= 2
    latest = workspace.client.get(f"/api/v1/projects/{project_id}/activity").json()["events"][0]
    assert activity["latest_at"] == latest["occurred_at"]


def test_projects_the_actor_is_not_a_member_of_never_appear(workspace: Workspace) -> None:
    mine = workspace.project("Library app", Role.VIEWER)
    theirs = workspace.project("Lab bookings")
    workspace.furnish(theirs)
    workspace.with_roles(theirs)

    body = workspace.my_work()

    assert [p["id"] for p in body["projects"]] == [mine]
    assert body["roles"][0] == {"role": "approver", "projects": 0, "waiting": 0}


def test_without_projects_the_summary_is_empty(workspace: Workspace) -> None:
    body = workspace.my_work()

    assert body["projects"] == []
    assert [total["projects"] for total in body["roles"]] == [0, 0, 0]


def test_the_number_of_queries_does_not_grow_with_the_number_of_projects(
    workspace: Workspace,
) -> None:
    def queries() -> int:
        engine = workspace.client.app.state.engine  # type: ignore[attr-defined]
        statements: list[str] = []

        def count(_conn: Connection, _cursor: object, statement: str, *_args: object) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", count)
        try:
            workspace.my_work()
        finally:
            event.remove(engine, "before_cursor_execute", count)
        return len(statements)

    first = workspace.project("Project 1")
    workspace.furnish(first)
    with_one = queries()
    for number in range(2, 6):
        project_id = workspace.project(f"Project {number}")
        workspace.furnish(project_id)

    with_five = queries()

    assert len(workspace.my_work()["projects"]) == 5
    assert with_five == with_one


def test_activity_older_than_the_window_is_left_out(workspace: Workspace) -> None:
    project_id = workspace.project("Library app", Role.VIEWER)
    with _session(workspace.database_url) as session:
        session.add(
            AuditEventRecord(
                id=new_id(),
                project_id=UUID(project_id),
                actor_kind="agent",
                actor_user_id=None,
                actor_name=None,
                type="run.failed",
                subjects=[],
                summary="A run failed",
                occurred_at=utc_now() - timedelta(days=8),
            )
        )

    assert workspace.entry(project_id)["recent_activity"] is None
