"""Editing a draft backlog, checking it and approving it as an immutable baseline, through the
API and the database. The drafts are synthetic and cite the stored room-booking sources."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID
from scopesteps.backlog.client import (
    BacklogVersionId,
    CandidateProposal,
    Evidence,
    ProposedCriterion,
    ProposedDecision,
    ProposedItem,
    save_candidate,
)
from scopesteps.backlog.infrastructure.orm import VersionRecord
from scopesteps.change_control.http import router as change_control_router
from scopesteps.change_control.infrastructure.orm import ApprovalRecord
from scopesteps.change_control.infrastructure.repository import SqlDecisionStore
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

BRIEF = (
    b"# Room booking\n\nStudents book study rooms one slot at a time.\n\n"
    b"Bookings may be cancelled before they start."
)
TRANSCRIPT = b"**Dana:** A booking lasts at most four hours.\n\n**Lee:** I said three hours."
LENGTH = "Maximum booking length"


@contextmanager
def _session(database_url: str) -> Generator[Session]:
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        yield session
        session.commit()
    engine.dispose()


class Backlog:
    """The demo project with two sources and drafts saved as an agent run would save them."""

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
        self.source_versions = [UUID(v["id"]) for v in response.json()["source_versions"]]
        self.blocks = [self._blocks(version) for version in self.source_versions]

    def _blocks(self, source_version_id: UUID) -> list[UUID]:
        url = f"/api/v1/projects/{DEMO_PROJECT_ID}/sources/{source_version_id}/blocks"
        return [UUID(block["id"]) for block in self.client.get(url).json()]

    def save_draft(
        self, *, open_length: bool = False, base: BacklogVersionId | None = None
    ) -> Json:
        """A draft with one source-backed criterion, one agent suggestion, a criterion a
        reviewer's answer confirmed, and (if `open_length`) a skipped conflict."""
        brief, transcript = self.source_versions
        booking = Evidence(brief, self.blocks[0][1])
        cancelling = Evidence(brief, self.blocks[0][2])
        decisions = [
            ProposedDecision(
                key="A1",
                kind="missing_decision",
                status="answered",
                subject="Cancellation",
                question="How late may a user cancel?",
                why_it_matters="No rule is agreed.",
                evidence=(cancelling,),
                affects=("S2",),
                answer="Up to one hour before the start.",
                decided_by=LOCAL_REVIEWER_ID,
                decided_at=utc_now(),
            )
        ]
        if open_length:
            decisions.append(
                ProposedDecision(
                    key="Q1",
                    kind="conflict",
                    status="skipped",
                    subject=LENGTH,
                    question="Is the maximum three or four hours?",
                    why_it_matters="The speakers disagree.",
                    evidence=(Evidence(transcript, self.blocks[1][0]),),
                    affects=("S1",),
                    decided_by=LOCAL_REVIEWER_ID,
                    decided_at=utc_now(),
                )
            )
        proposal = CandidateProposal(
            project_id=DEMO_PROJECT_ID,
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
                            "A student books one slot.", proposed=False, evidence=(booking,)
                        ),
                        ProposedCriterion("The student sees a confirmation.", proposed=True),
                    ),
                ),
                ProposedItem(
                    "S2",
                    "story",
                    "E1",
                    "Cancel a booking",
                    "As a student, I want to cancel, so that others can book.",
                    criteria=(
                        ProposedCriterion(
                            "A booking can be cancelled up to one hour before it starts.",
                            proposed=False,
                            confirmed_by=("A1",),
                        ),
                    ),
                ),
            ),
            decisions=tuple(decisions),
        )
        with _session(self.database_url) as session:
            version_id = save_candidate(session, proposal, utc_now())
            if base is not None:
                record = session.get_one(VersionRecord, version_id)
                record.base_version_id = base
        return self.get(version_id)

    def key(self) -> str:
        self.keys += 1
        return f"approval-test-key-{self.keys:04d}"

    def get(self, version_id: object) -> Json:
        response = self.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/backlogs/{version_id}")
        assert response.status_code == 200, response.text
        return response.json()

    def patch(self, draft: Json, item: Json, key: str | None = None, **body: Any) -> Response:
        return self.client.patch(
            f"/api/v1/backlogs/{draft['id']}/items/{item['id']}",
            json={"expected_revision": draft["revision"], **body},
            headers={"Idempotency-Key": key or self.key()},
        )

    def review(self, draft: Json, revision: int | None = None) -> Response:
        return self.client.post(
            f"/api/v1/backlogs/{draft['id']}/review",
            json={"expected_revision": revision or draft["revision"]},
            headers={"Idempotency-Key": self.key()},
        )

    def approve(self, draft: Json, key: str | None = None, **overrides: Any) -> Response:
        body = {
            "expected_revision": draft["revision"],
            "content_hash": draft["content_hash"],
            "expected_baseline_id": draft["base_version_id"],
        } | overrides
        return self.client.post(
            f"/api/v1/backlogs/{draft['id']}/approve",
            json=body,
            headers={"Idempotency-Key": key or self.key()},
        )

    def reject(self, draft: Json, key: str | None = None) -> Response:
        return self.client.post(
            f"/api/v1/backlogs/{draft['id']}/reject",
            json={"expected_revision": draft["revision"], "reason": "Not this quarter."},
            headers={"Idempotency-Key": key or self.key()},
        )

    def answer(self, draft: Json, decision: Json, answer: str, key: str | None = None) -> Response:
        return self.client.patch(
            f"/api/v1/backlogs/{draft['id']}/decisions/{decision['id']}",
            json={"expected_revision": draft["revision"], "answer": answer},
            headers={"Idempotency-Key": key or self.key()},
        )

    def settle_suggestion(self, draft: Json, status: str = "accepted") -> Json:
        """Accept or reject the agent suggestion on "Book a room"; returns the new draft."""
        story = _item(draft, "Book a room")
        criteria = [{"id": c["id"], "text": c["text"]} for c in story["criteria"]]
        criteria[1]["suggestion"] = status
        response = self.patch(draft, story, criteria=criteria)
        assert response.status_code == 200, response.text
        return response.json()

    def ready_draft(self) -> Json:
        return self.settle_suggestion(self.save_draft())

    def project(self) -> Json:
        return self.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}").json()

    def events(self, event_type: str) -> list[Json]:
        feed = self.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/activity").json()
        return [event for event in feed["events"] if event["type"] == event_type]

    def approvals(self) -> int:
        with _session(self.database_url) as session:
            return session.scalar(select(func.count()).select_from(ApprovalRecord)) or 0

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
def backlog(
    client: TestClient, seeded_database_url: str, confirm_speakers: Callable[[TestClient], None]
) -> Backlog:
    backlog_ = Backlog(client, seeded_database_url)
    confirm_speakers(client)
    return backlog_


def _item(version: Json, title: str) -> Json:
    return next(item for item in version["items"] if item["title"] == title)


def _error(response: Response, status: int, code: str) -> Json:
    assert (response.status_code, response.json()["code"]) == (status, code), response.text
    body: Json = response.json()
    return body


def test_an_edit_keeps_stable_ids_and_records_who_made_it(backlog: Backlog) -> None:
    draft = backlog.save_draft()
    story = _item(draft, "Book a room")
    sourced, suggestion = story["criteria"]

    response = backlog.patch(
        draft,
        story,
        title="Book a study room",
        criteria=[
            {"id": sourced["id"], "text": "A signed-in student books one slot."},
            {"id": suggestion["id"], "text": suggestion["text"]},
            {"text": "Rooms show their capacity."},
        ],
    )

    assert response.status_code == 200, response.text
    edited = response.json()
    assert (edited["revision"], edited["state"]) == (2, "draft")
    assert edited["content_hash"] != draft["content_hash"]
    assert [item["id"] for item in edited["items"]] == [item["id"] for item in draft["items"]]
    story = _item(edited, "Book a study room")
    assert (story["human_edited"], story["edited_by"]) == (True, str(LOCAL_REVIEWER_ID))
    first, second, added = story["criteria"]
    assert (first["id"], first["origin"], first["evidence"]) == (
        sourced["id"],
        "source",
        sourced["evidence"],
    )
    assert first["edited_by"] == str(LOCAL_REVIEWER_ID)
    assert (second["id"], second["edited_by"], second["suggestion"]) == (
        suggestion["id"],
        None,
        "pending",
    )
    assert (added["origin"], added["suggestion"], added["edited_by"]) == (
        "person",
        None,
        str(LOCAL_REVIEWER_ID),
    )
    assert added["id"] not in {sourced["id"], suggestion["id"]}
    assert backlog.get(draft["id"]) == edited, "the edit is stored as returned"
    (event,) = backlog.events("backlog.item_edited")
    assert event["summary"] == (
        "Edited a story in draft revision 1: changed the title, added 1 criterion, "
        "edited 1 criterion"
    )
    assert [s["kind"] for s in event["subjects"]] == ["backlog_version", "item"]


def test_accepting_or_rejecting_a_suggestion_clears_its_blocker(backlog: Backlog) -> None:
    draft = backlog.save_draft()
    assert [b["code"] for b in _item(draft, "Book a room")["blockers"]] == ["proposed_criterion"]

    rejected = backlog.settle_suggestion(draft, "rejected")

    story = _item(rejected, "Book a room")
    assert story["blockers"] == []
    assert story["criteria"][1]["suggestion"] == "rejected"
    assert story["human_edited"] is False, "reviewing a suggestion does not edit the story"
    assert backlog.events("backlog.item_edited")[0]["summary"].endswith("rejected 1 suggestion")


def test_a_stale_edit_is_a_conflict_and_changes_nothing(backlog: Backlog) -> None:
    draft = backlog.save_draft()
    backlog.settle_suggestion(draft)
    before = backlog.get(draft["id"])

    response = backlog.patch(draft, _item(draft, "Book a room"), title="Book any room")

    body = _error(response, 409, "VERSION_CHANGED")
    assert body["details"]["current_revision"] == 2
    assert backlog.get(draft["id"]) == before


def test_a_repeated_edit_is_applied_once(backlog: Backlog) -> None:
    draft = backlog.save_draft()
    story = _item(draft, "Book a room")

    first = backlog.patch(draft, story, key="edit-key-0001", title="Book a study room")
    again = backlog.patch(draft, story, key="edit-key-0001", title="Book a study room")
    reused = backlog.patch(draft, story, key="edit-key-0001", title="Something else")

    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json() == first.json()
    assert again.json()["revision"] == 2
    _error(reused, 409, "IDEMPOTENCY_KEY_REUSED")
    assert len(backlog.events("backlog.item_edited")) == 1


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"title": ""}, 422, "VALIDATION_ERROR"),
        ({"criteria": [{"id": str(UUID(int=5)), "text": "x"}]}, 422, "ITEM_EDIT_INVALID"),
        ({"criteria": [{"text": "x", "suggestion": "accepted"}]}, 422, "ITEM_EDIT_INVALID"),
        ({"expected_revision": 0}, 422, "VALIDATION_ERROR"),
    ],
)
def test_an_invalid_edit_is_refused(backlog: Backlog, body: Json, status: int, code: str) -> None:
    draft = backlog.save_draft()

    response = backlog.patch(draft, _item(draft, "Book a room"), **body)

    _error(response, status, code)
    assert backlog.get(draft["id"]) == draft


def test_an_unknown_item_or_version_is_not_found(backlog: Backlog) -> None:
    draft = backlog.save_draft()

    unknown_item = backlog.patch(draft, {"id": str(new_id())}, title="x")
    unknown_version = backlog.patch(
        draft | {"id": str(new_id())}, _item(draft, "Book a room"), title="x"
    )

    _error(unknown_item, 404, "NOT_FOUND")
    assert _error(unknown_version, 404, "NOT_FOUND")["message"] == "Backlog version not found"


@pytest.mark.parametrize(
    ("roles", "status"),
    [((), 404), ((Role.VIEWER,), 403), ((Role.APPROVER,), 403), ((Role.EDITOR,), 200)],
)
def test_only_an_editor_may_edit(backlog: Backlog, roles: tuple[Role, ...], status: int) -> None:
    draft = backlog.save_draft()
    backlog.hold_roles(*roles)

    response = backlog.patch(draft, _item(draft, "Book a room"), title="Book a study room")

    assert response.status_code == status, response.text


def test_review_reports_every_check_and_whether_the_draft_is_ready(backlog: Backlog) -> None:
    draft = backlog.save_draft(open_length=True)

    response = backlog.review(draft)

    assert response.status_code == 200, response.text
    review = response.json()
    assert {c["code"]: c["passed"] for c in review["checks"]} == {
        "structure_valid": True,
        "citations_resolve": True,
        "suggestions_reviewed": False,
        "decisions_resolved": False,
    }
    assert [c["title"] for c in review["checks"]] == [
        "Structure is valid",
        "Every citation resolves",
        "Every agent suggestion is reviewed",
        "No decision is open",
    ]
    assert review["ready"] is False
    assert (review["revision"], review["content_hash"]) == (1, draft["content_hash"])
    assert (review["epic_count"], review["story_count"]) == (1, 2)
    assert review["baseline_version_id"] is None
    assert {b["code"] for b in review["blockers"]} == {"proposed_criterion", "unresolved_conflict"}


def test_a_settled_draft_is_ready_and_any_member_may_check_it(backlog: Backlog) -> None:
    draft = backlog.ready_draft()
    backlog.hold_roles(Role.VIEWER)

    review = backlog.review(draft).json()

    assert review["ready"] is True
    assert all(check["passed"] for check in review["checks"])


def test_reviewing_a_stale_revision_is_a_conflict(backlog: Backlog) -> None:
    draft = backlog.save_draft()
    backlog.settle_suggestion(draft)

    _error(backlog.review(draft), 409, "VERSION_CHANGED")


def test_approval_freezes_the_draft_as_baseline_v1_in_one_step(backlog: Backlog) -> None:
    draft = backlog.settle_suggestion(backlog.save_draft(), "rejected")

    response = backlog.approve(draft)

    assert response.status_code == 200, response.text
    decision = response.json()
    assert decision | {"id": None, "decided_at": None} == {
        "id": None,
        "version_id": draft["id"],
        "decision": "approved",
        "decided_by": str(LOCAL_REVIEWER_ID),
        "revision": 2,
        "content_hash": draft["content_hash"],
        "decided_at": None,
        "baseline_version": 1,
        "current_baseline_id": draft["id"],
        "change_request_id": None,
        "change_request_status": None,
    }
    approved = backlog.get(draft["id"])
    assert (approved["state"], approved["revision"], approved["content_hash"]) == (
        "approved",
        2,
        draft["content_hash"],
    )
    story = _item(approved, "Book a room")
    assert [c["origin"] for c in story["criteria"]] == ["source"], "the rejected one is left out"
    status = backlog.project()["status"]
    assert (status["state"], status["baseline_version"], status["baseline_version_id"]) == (
        "baseline",
        1,
        draft["id"],
    )
    (event,) = backlog.events("backlog.approved")
    assert event["summary"] == (
        "Approved baseline v1 from draft revision 2, with 1 epic and 2 stories"
    )
    assert {s["kind"]: s["id"] for s in event["subjects"]} == {
        "backlog_version": draft["id"],
        "approval": decision["id"],
    }


def test_an_approved_version_never_changes_and_survives_a_restart(
    backlog: Backlog, make_client: ClientFactory
) -> None:
    draft = backlog.ready_draft()
    backlog.approve(draft)
    approved = backlog.get(draft["id"])

    edit = backlog.patch(approved, _item(approved, "Book a room"), title="Book any room")
    again = backlog.approve(approved)
    rejected = backlog.reject(approved)
    restarted = make_client(backlog.database_url)
    after = restarted.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/backlogs/{draft['id']}").json()

    for response in (edit, again, rejected):
        assert _error(response, 409, "VERSION_NOT_DRAFT")["details"] == {"state": "approved"}
    assert after == approved
    assert backlog.approvals() == 1


def test_approval_is_refused_until_every_check_passes(backlog: Backlog) -> None:
    draft = backlog.settle_suggestion(backlog.save_draft(open_length=True))

    response = backlog.approve(draft)

    body = _error(response, 409, "APPROVAL_BLOCKED")
    failed = [check["code"] for check in body["details"]["checks"] if not check["passed"]]
    assert failed == ["decisions_resolved"]
    assert backlog.get(draft["id"]) == draft
    assert backlog.project()["status"]["state"] == "draft_in_progress"
    assert (backlog.approvals(), backlog.events("backlog.approved")) == (0, [])


def test_approval_is_refused_when_a_citation_no_longer_resolves(backlog: Backlog) -> None:
    draft = backlog.ready_draft()
    with _session(backlog.database_url) as session:
        record = session.get_one(VersionRecord, UUID(draft["id"]))
        record.source_version_ids = [str(backlog.source_versions[1])]

    body = _error(backlog.approve(draft), 409, "APPROVAL_BLOCKED")

    citations = next(c for c in body["details"]["checks"] if c["code"] == "citations_resolve")
    assert citations["passed"] is False
    assert "which the draft was not made from" in citations["problems"][0]


@pytest.mark.parametrize(
    ("roles", "status"),
    [((), 404), ((Role.VIEWER,), 403), ((Role.EDITOR,), 403)],
)
def test_only_an_approver_may_approve_or_reject(
    backlog: Backlog, roles: tuple[Role, ...], status: int
) -> None:
    draft = backlog.ready_draft()
    backlog.hold_roles(*roles)

    approve = backlog.approve(draft)
    reject = backlog.reject(draft)

    assert (approve.status_code, reject.status_code) == (status, status)
    backlog.hold_roles(Role.VIEWER)
    assert backlog.get(draft["id"]) == draft
    assert backlog.approvals() == 0


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"expected_revision": 1}, "VERSION_CHANGED"),
        ({"content_hash": "0" * 64}, "VERSION_CHANGED"),
        ({"expected_baseline_id": str(UUID(int=1))}, "BASELINE_CHANGED"),
    ],
)
def test_a_stale_approval_is_a_conflict_and_changes_nothing(
    backlog: Backlog, overrides: Json, code: str
) -> None:
    draft = backlog.ready_draft()

    _error(backlog.approve(draft, **overrides), 409, code)

    assert backlog.get(draft["id"]) == draft
    assert backlog.approvals() == 0


def test_a_repeated_approval_returns_the_same_decision(backlog: Backlog) -> None:
    draft = backlog.ready_draft()

    first = backlog.approve(draft, key="approve-key-0001")
    again = backlog.approve(draft, key="approve-key-0001")
    reused = backlog.reject(draft, key="approve-key-0001")

    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json() == first.json()
    _error(reused, 409, "IDEMPOTENCY_KEY_REUSED")
    assert backlog.approvals() == 1
    assert len(backlog.events("backlog.approved")) == 1


def test_a_second_draft_from_the_same_baseline_cannot_advance_it_again(
    backlog: Backlog,
) -> None:
    first = backlog.ready_draft()
    second = backlog.ready_draft()
    backlog.approve(first)

    response = backlog.approve(second)

    body = _error(response, 409, "BASELINE_CHANGED")
    assert body["details"]["current_baseline_id"] == first["id"]
    assert backlog.get(second["id"])["state"] == "draft"
    assert backlog.project()["status"]["baseline_version"] == 1


def test_a_concurrent_approval_that_read_the_same_baseline_loses_and_stores_nothing(
    backlog: Backlog, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = backlog.ready_draft()
    second = backlog.ready_draft()
    backlog.approve(first)

    class ReadBeforeTheOtherCommitted(SqlDecisionStore):
        def current_baseline(self, project_id: ProjectId) -> None:
            return None

    monkeypatch.setattr(change_control_router, "SqlDecisionStore", ReadBeforeTheOtherCommitted)
    response = backlog.approve(second)

    _error(response, 409, "DECISION_IN_PROGRESS")
    assert response.json()["retryable"] is True
    assert backlog.get(second["id"]) == second
    assert backlog.approvals() == 1
    assert len(backlog.events("backlog.approved")) == 1


def test_a_failed_audit_write_rolls_the_whole_approval_back(
    backlog: Backlog, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft = backlog.ready_draft()

    class BrokenRecorder:
        def record(self, **_: object) -> None:
            raise RuntimeError("audit store unavailable")

    def broken_recorder(_session: Session) -> BrokenRecorder:
        return BrokenRecorder()

    monkeypatch.setattr(change_control_router, "audit_recorder", broken_recorder)
    with pytest.raises(RuntimeError, match="audit store unavailable"):
        backlog.approve(draft)

    assert backlog.get(draft["id"]) == draft
    assert backlog.approvals() == 0
    assert backlog.project()["status"]["baseline_version"] is None


def test_a_change_draft_based_on_v1_becomes_v2(backlog: Backlog) -> None:
    v1 = backlog.ready_draft()
    backlog.approve(v1)
    change = backlog.settle_suggestion(backlog.save_draft(base=BacklogVersionId(UUID(v1["id"]))))

    response = backlog.approve(change, expected_baseline_id=v1["id"])

    assert response.status_code == 200, response.text
    assert (response.json()["baseline_version"], response.json()["current_baseline_id"]) == (
        2,
        change["id"],
    )
    assert backlog.get(v1["id"])["state"] == "approved", "v1 stays as it was"
    assert backlog.project()["status"]["baseline_version_id"] == change["id"]


def test_a_rejection_leaves_the_baseline_and_keeps_its_reason_out_of_the_log(
    backlog: Backlog,
) -> None:
    v1 = backlog.ready_draft()
    backlog.approve(v1)
    change = backlog.save_draft(base=BacklogVersionId(UUID(v1["id"])))

    response = backlog.reject(change)

    assert response.status_code == 200, response.text
    decision = response.json()
    assert (decision["decision"], decision["baseline_version"]) == ("rejected", None)
    assert decision["current_baseline_id"] == v1["id"]
    assert backlog.get(change["id"])["state"] == "rejected"
    status = backlog.project()["status"]
    assert (status["state"], status["baseline_version_id"]) == ("baseline", v1["id"])
    (event,) = backlog.events("backlog.rejected")
    assert event["summary"] == "Rejected draft revision 1; the baseline is unchanged"
    assert "quarter" not in event["summary"]
    with _session(backlog.database_url) as session:
        stored = session.scalars(
            select(ApprovalRecord).where(ApprovalRecord.decision == "rejected")
        ).one()
        assert stored.reason == "Not this quarter."


def _decision(version: Json, status: str) -> Json:
    return next(d for d in version["decisions"] if d["status"] == status)


def test_a_decision_skipped_in_the_run_can_be_answered_and_then_approved(
    backlog: Backlog,
) -> None:
    draft = backlog.settle_suggestion(backlog.save_draft(open_length=True))
    skipped = _decision(draft, "skipped")

    response = backlog.answer(draft, skipped, "  Four hours, as the room policy says.  ")

    assert response.status_code == 200, response.text
    answered = response.json()
    decision = next(d for d in answered["decisions"] if d["id"] == skipped["id"])
    assert decision["status"] == "answered"
    assert decision["answer"] == "Four hours, as the room policy says."
    assert decision["decided_by"] == str(LOCAL_REVIEWER_ID)
    assert answered["revision"] == draft["revision"] + 1
    assert answered["content_hash"] != draft["content_hash"]
    assert "unresolved_conflict" not in {b["code"] for b in answered["blockers"]}
    assert backlog.review(answered).json()["ready"] is True
    assert backlog.approve(answered).status_code == 200
    [event] = backlog.events("scope.decided")
    assert "Four hours" not in event["summary"]


def test_an_answered_decision_keeps_its_answer(backlog: Backlog) -> None:
    draft = backlog.save_draft()

    response = backlog.answer(draft, _decision(draft, "answered"), "Two hours before.")

    _error(response, 409, "DECISION_ALREADY_ANSWERED")
    assert backlog.get(draft["id"]) == draft


@pytest.mark.parametrize(
    "answer",
    ["", "   ", "x" * 2001, "Ring the bell\x07"],
    ids=["empty", "blank", "long", "control"],
)
def test_an_invalid_answer_is_refused_and_changes_nothing(backlog: Backlog, answer: str) -> None:
    draft = backlog.save_draft(open_length=True)

    response = backlog.answer(draft, _decision(draft, "skipped"), answer)

    _error(response, 422, "DECISION_ANSWER_INVALID")
    assert backlog.get(draft["id"]) == draft
    assert backlog.events("scope.decided") == []


def test_a_stale_answer_is_a_conflict_and_changes_nothing(backlog: Backlog) -> None:
    draft = backlog.save_draft(open_length=True)
    backlog.settle_suggestion(draft)

    response = backlog.answer(draft, _decision(draft, "skipped"), "Four hours.")

    _error(response, 409, "VERSION_CHANGED")
    assert _decision(backlog.get(draft["id"]), "skipped")["id"] == _decision(draft, "skipped")["id"]


def test_a_repeated_answer_is_applied_once(backlog: Backlog) -> None:
    draft = backlog.save_draft(open_length=True)
    skipped = _decision(draft, "skipped")

    first = backlog.answer(draft, skipped, "Four hours.", key="answer-key-0001")
    retry = backlog.answer(draft, skipped, "Four hours.", key="answer-key-0001")
    reused = backlog.answer(draft, skipped, "Three hours.", key="answer-key-0001")

    assert (first.status_code, retry.status_code) == (200, 200)
    assert retry.json() == first.json()
    _error(reused, 409, "IDEMPOTENCY_KEY_REUSED")
    assert len(backlog.events("scope.decided")) == 1


@pytest.mark.parametrize(
    ("roles", "status"),
    [
        ((), 404),
        ((Role.VIEWER,), 403),
        ((Role.EDITOR,), 200),
        ((Role.APPROVER,), 200),
    ],
    ids=["non-member", "viewer", "editor", "approver"],
)
def test_an_editor_or_approver_may_answer_a_decision(
    backlog: Backlog, roles: tuple[Role, ...], status: int
) -> None:
    draft = backlog.save_draft(open_length=True)
    backlog.hold_roles(*roles)

    response = backlog.answer(draft, _decision(draft, "skipped"), "Four hours.")

    assert response.status_code == status, response.text


def test_an_unknown_decision_is_not_found(backlog: Backlog) -> None:
    draft = backlog.save_draft()

    response = backlog.answer(draft, {"id": str(new_id())}, "Four hours.")

    assert response.status_code == 404


def test_a_decision_on_an_approved_version_cannot_be_answered(backlog: Backlog) -> None:
    draft = backlog.ready_draft()
    approved = backlog.approve(draft)
    assert approved.status_code == 200, approved.text
    current = backlog.get(draft["id"])

    response = backlog.answer(current, _decision(current, "answered"), "Two hours.")

    _error(response, 409, "VERSION_NOT_DRAFT")
