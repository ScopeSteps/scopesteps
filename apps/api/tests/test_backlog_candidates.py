"""An initial run over the room-booking sources, from clarification to a saved draft backlog.

The model is scripted from `fixtures/room_booking`; no test makes a live call.
"""

import copy
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from scopesteps.agent.client import RunLimits
from scopesteps.agent.domain.model import ModelResult, ModelTurn, ToolCall, Usage
from scopesteps.agent.http import router as agent_router
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.agent.infrastructure.repository import SqlCandidateStore
from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID
from scopesteps.backlog.client import (
    CandidateProposal,
    CandidateRejectedError,
    Evidence,
    ProposedCriterion,
    ProposedItem,
    candidate_problems,
    save_candidate,
)
from scopesteps.backlog.infrastructure.orm import VersionRecord
from scopesteps.identity.client import Role
from scopesteps.identity.domain.user import Membership
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
from scopesteps.sources.client import quote_matches

FIXTURE = Path(__file__).parent / "fixtures" / "room_booking"
CLARIFICATION: dict[str, Any] = json.loads((FIXTURE / "clarification.json").read_text())
DRAFT: dict[str, Any] = json.loads((FIXTURE / "draft.json").read_text())
CANCELLATION, LENGTH = "Cancellation and no-shows", "Maximum booking length"
CANCEL_ANSWER = (
    "Users can cancel up to one hour before the start. Cancelling later counts as a no-show."
)
NO_CHANGES: dict[str, list[Any]] = {"statements": [], "items": [], "questions": []}
MODEL = "gemini-3.5-flash-lite"
LIMITS = RunLimits(
    max_turns=6, max_tool_calls=8, max_output_tokens_per_call=8000, max_total_tokens=200_000
)
Json = dict[str, Any]


def _result(text: str = "", calls: tuple[ToolCall, ...] = ()) -> ModelResult:
    return ModelResult(
        provider="test",
        model_id=MODEL,
        turn=ModelTurn(({"type": "model_output", "text": text},)),
        text=text or None,
        tool_calls=calls,
        finish_reason="tool_calls" if calls else "completed",
        usage=Usage(input_tokens=1000, output_tokens=100, total_tokens=1100),
        latency_ms=50,
    )


class RoomBooking:
    """The room-booking project with both sources uploaded and a scripted model."""

    def __init__(self, client: TestClient, database_url: str) -> None:
        self.client = client
        self.database_url = database_url
        self.keys = 0
        self.source_version_ids = self.upload(DEMO_PROJECT_ID)

    def upload(self, project_id: UUID) -> list[str]:
        response = self.client.post(
            f"/api/v1/projects/{project_id}/sources",
            files={
                "brief": ("brief.md", (FIXTURE / "brief.md").read_bytes()),
                "transcript": ("transcript.md", (FIXTURE / "transcript.md").read_bytes()),
            },
            headers={"Idempotency-Key": self.key()},
        )
        assert response.status_code == 201, response.text
        return [version["id"] for version in response.json()["source_versions"]]

    def key(self) -> str:
        self.keys += 1
        return f"room-booking-key-{self.keys:04d}"

    def post(self, path: str, body: Json | None = None) -> Json:
        response = self.client.post(
            f"/api/v1{path}", json=body, headers={"Idempotency-Key": self.key()}
        )
        assert response.status_code < 300, response.text
        return response.json()

    def get(self, path: str) -> Json:
        response = self.client.get(f"/api/v1{path}")
        assert response.status_code == 200, response.text
        return response.json()

    def review(
        self,
        draft: Json = DRAFT,
        *,
        repair: Json | str | None = None,
        answers: dict[str, str | None] | None = None,
    ) -> Json:
        """Run to the end: the agent asks both questions, the reviewer answers the cancellation
        one and skips the length one (unless `answers` says otherwise), then the draft arrives."""
        ask = _result(calls=(ToolCall("call-1", "request_clarification", CLARIFICATION),))
        script = [ask, _result("READY"), _result(json.dumps(draft))]
        if repair is not None:
            script.append(_result(repair if isinstance(repair, str) else json.dumps(repair)))
        self.script(script)
        run = self.post(
            f"/projects/{DEMO_PROJECT_ID}/runs",
            {"mode": "initial", "source_version_ids": self.source_version_ids},
        )
        waiting = self.post(f"/runs/{run['id']}/advance")
        assert waiting["status"] == "waiting_for_input", waiting
        replies = {CANCELLATION: CANCEL_ANSWER, LENGTH: None} | (answers or {})
        for question in waiting["questions"]:
            reply = replies[question["subject"]]
            body = {"question_id": question["id"]} | (
                {"answer": reply} if reply else {"skip": True}
            )
            self.post(f"/runs/{run['id']}/answers", body)
        self.post(f"/runs/{run['id']}/advance")
        return self.post(f"/runs/{run['id']}/advance")

    def script(self, results: list[ModelResult]) -> None:
        self.client.app.state.agent_runtime = replace(  # type: ignore[attr-defined]
            self.client.app.state.agent_runtime,  # type: ignore[attr-defined]
            provider=ScriptedProvider(results),
            provider_name="gemini",
            model_id=MODEL,
            limits=LIMITS,
        )

    def backlog(self, run: Json) -> Json:
        assert run["status"] == "ready_for_review", run
        return self.get(f"/projects/{DEMO_PROJECT_ID}/backlogs/{run['candidate_version_id']}")

    def passage(self, source_version_id: str, block_id: str) -> Json:
        blocks: list[Json] = self.client.get(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/sources/{source_version_id}/blocks"
        ).json()
        return next(block for block in blocks if block["id"] == block_id)

    def session(self) -> Any:
        return create_session_factory(create_database_engine(self.database_url))()


@pytest.fixture
def rooms(client: TestClient, seeded_database_url: str) -> RoomBooking:
    return RoomBooking(client, seeded_database_url)


def _item(backlog: Json, title: str) -> Json:
    return next(item for item in backlog["items"] if item["title"] == title)


def _decision(backlog: Json, subject: str) -> Json:
    return next(decision for decision in backlog["decisions"] if decision["subject"] == subject)


def _edited(change: Callable[[Json], None]) -> Json:
    draft = copy.deepcopy(DRAFT)
    change(draft)
    return draft


def _story(draft: Json, ref: str) -> Json:
    return next(item for item in draft["items"] if item["ref"] == ref)


def test_a_reviewed_run_saves_a_draft_backlog_within_the_ceilings(rooms: RoomBooking) -> None:
    run = rooms.review()

    backlog = rooms.backlog(run)

    assert run["problems"] == []
    assert (backlog["state"], backlog["revision"], backlog["base_version_id"]) == ("draft", 1, None)
    assert (backlog["run_id"], backlog["source_version_ids"]) == (
        run["id"],
        rooms.source_version_ids,
    )
    assert len(backlog["content_hash"]) == 64
    epics = {item["id"] for item in backlog["items"] if item["kind"] == "epic"}
    stories = [item for item in backlog["items"] if item["kind"] == "story"]
    assert (len(epics), len(stories)) == (2, 5), (
        "what the sources confirm, not eight to fill a quota"
    )
    assert all(story["parent_id"] in epics for story in stories)
    assert len({item["id"] for item in backlog["items"]}) == 7


def test_every_citation_opens_its_exact_stored_passage(rooms: RoomBooking) -> None:
    backlog = rooms.backlog(rooms.review())

    evidence = [
        *(e for item in backlog["items"] for c in item["criteria"] for e in c["evidence"]),
        *(e for decision in backlog["decisions"] for e in decision["evidence"]),
        *(e for note in backlog["out_of_scope"] for e in note["evidence"]),
    ]

    assert len(evidence) >= 12
    for reference in evidence:
        assert reference["source_version_id"] in rooms.source_version_ids
        passage = rooms.passage(reference["source_version_id"], reference["block_id"])
        if reference["quote"] is not None:
            assert quote_matches(reference["quote"], passage["text"]), reference
    overlap = _item(backlog, "Search for and book a one-off slot")["criteria"][1]["evidence"][0]
    cited = rooms.passage(overlap["source_version_id"], overlap["block_id"])
    assert cited["text"].startswith("**Priya (IT):** The booking service will reject")


def test_claims_are_labelled_source_backed_reviewer_confirmed_or_proposed(
    rooms: RoomBooking,
) -> None:
    backlog = rooms.backlog(rooms.review())

    booking = _item(backlog, "Search for and book a one-off slot")
    cancelling = _item(backlog, "Cancel a booking")
    answered = _decision(backlog, CANCELLATION)

    assert [c["origin"] for c in booking["criteria"]] == ["source", "source", "proposed"]
    proposed = booking["criteria"][2]
    assert (proposed["evidence"], proposed["confirmed_by"]) == ([], [])
    assert {"proposed_criterion": proposed["id"]}.items() <= {
        b["code"]: b["criterion_id"] for b in booking["blockers"]
    }.items()
    assert [c["origin"] for c in cancelling["criteria"]] == ["human", "human"]
    assert all(c["confirmed_by"] == [answered["id"]] for c in cancelling["criteria"])
    assert (answered["status"], answered["answer"]) == ("answered", CANCEL_ANSWER)
    assert answered["decided_by"] == str(LOCAL_REVIEWER_ID)
    assert datetime.fromisoformat(answered["decided_at"]).tzinfo is not None
    assert answered["affected_item_ids"] == [cancelling["id"]]
    assert cancelling["blockers"] == [], "a confirmed answer blocks nothing"


def test_recurring_reservations_are_recorded_as_excluded_not_as_backlog(rooms: RoomBooking) -> None:
    backlog = rooms.backlog(rooms.review())

    excluded, suggested = backlog["out_of_scope"]

    assert (excluded["kind"], suggested["kind"]) == ("excluded", "suggested")
    assert "Recurring reservations are out of scope" in excluded["summary"]
    said = rooms.passage(
        excluded["evidence"][1]["source_version_id"], excluded["evidence"][1]["block_id"]
    )
    assert (
        said["text"]
        == "**Alex (Product owner):** Agreed. Recurring reservations are out of scope for release one."
    )
    assert "Outlook" in suggested["summary"]
    for item in backlog["items"]:
        text = json.dumps(item).lower()
        assert not any(word in text for word in ("recurring", "weekly", "outlook"))


def test_a_conflict_blocks_the_story_it_affects_and_neither_value_is_stated(
    rooms: RoomBooking,
) -> None:
    backlog = rooms.backlog(rooms.review())

    booking = _item(backlog, "Search for and book a one-off slot")
    length = _decision(backlog, LENGTH)

    assert (length["kind"], length["status"], length["answer"]) == ("conflict", "skipped", None)
    assert length["affected_item_ids"] == [booking["id"]]
    assert length["decided_by"] == str(LOCAL_REVIEWER_ID), "who skipped it is recorded"
    conflicting = [e for e in length["evidence"] if e["relationship"] == "conflicting"]
    assert {e["quote"] for e in conflicting} == {
        "A booking can last up to 4 hours.",
        "three hours is the most I want for a single booking",
    }
    assert ("unresolved_conflict", length["id"]) in {
        (b["code"], b["decision_id"]) for b in booking["blockers"]
    }
    stated = " ".join(c["text"] for c in booking["criteria"]).lower()
    assert not any(value in stated for value in ("4 hours", "3 hours", "four", "three"))
    blocked = {b["item_id"] for b in backlog["blockers"] if b["code"] == "unresolved_conflict"}
    assert blocked == {booking["id"]}, "stories the conflict does not affect are not blocked"


def _both_skipped(draft: Json) -> None:
    """The draft the model writes when the cancellation question was skipped too (U1, U2)."""
    draft["statements"] = [s for s in draft["statements"] if s["id"] != "T9"]
    draft["items"] = [item for item in draft["items"] if item["ref"] != "S3"]
    not_answered = {"block_id": "U1", "quote": "The reviewer has not answered this yet"}
    draft["questions"][0]["citations"][0]["block_id"] = "U2"
    draft["questions"].append(
        {
            "subject": "Cancellation",
            "question": "How late may a user cancel?",
            "why_it_matters": "Still undecided.",
            "citations": [not_answered],
            "affects": [],
        }
    )


def test_an_answer_becomes_scope_and_a_skip_leaves_the_decision_open(rooms: RoomBooking) -> None:
    answered = rooms.backlog(rooms.review())
    skipped = rooms.backlog(rooms.review(_edited(_both_skipped), answers={CANCELLATION: None}))

    assert "Cancel a booking" in {item["title"] for item in answered["items"]}
    assert "Cancel a booking" not in {item["title"] for item in skipped["items"]}
    open_decision = _decision(skipped, CANCELLATION)
    assert (open_decision["status"], open_decision["answer"]) == ("skipped", None)
    assert open_decision["question"].startswith("How late may a user cancel a booking")
    assert {
        "code": "open_decision",
        "message": f"The reviewer skipped this decision: {CANCELLATION}",
        "item_id": None,
        "decision_id": open_decision["id"],
        "criterion_id": None,
    } in skipped["blockers"]
    assert "cancel" not in json.dumps(skipped["items"]).lower(), "no invented cancellation rule"
    assert _decision(skipped, LENGTH)["status"] == "skipped", "the other skip stays open too"


def test_a_skipped_question_stays_open_when_the_model_does_not_raise_it_again(
    rooms: RoomBooking,
) -> None:
    silent = _edited(lambda draft: draft.update(questions=[]))

    run = rooms.review(silent, repair=NO_CHANGES)
    backlog = rooms.backlog(run)

    assert any("open decision U1 is unresolved" in problem for problem in run["problems"])
    assert _decision(backlog, LENGTH)["status"] == "skipped"
    assert _decision(backlog, CANCELLATION)["status"] == "answered", (
        "the answer settled only itself"
    )
    booking = _item(backlog, "Search for and book a one-off slot")
    assert "unresolved_conflict" in {b["code"] for b in booking["blockers"]}
    assert "4 hours" not in json.dumps(booking["criteria"])


def _cite_missing_block(draft: Json) -> None:
    _story(draft, "S1")["criteria"][0]["citations"][0]["block_id"] = "B99"


def test_a_bad_reference_is_repaired_once_within_the_run_budget(rooms: RoomBooking) -> None:
    repaired = NO_CHANGES | {"items": [_story(DRAFT, "S1")]}

    run = rooms.review(_edited(_cite_missing_block), repair=repaired)
    signing_in = _item(rooms.backlog(run), "Sign in with a college account")

    assert run["problems"] == []
    assert run["usage"]["model_turns"] == 4, "ask, ready, draft and exactly one repair"
    assert signing_in["criteria"][0]["origin"] == "source"
    assert signing_in["criteria"][0]["evidence"][0]["quote"] == (
        "sign in with their existing college account"
    )


def test_a_bad_reference_the_repair_did_not_fix_is_never_saved_as_evidence(
    rooms: RoomBooking,
) -> None:
    run = rooms.review(_edited(_cite_missing_block), repair=NO_CHANGES)
    signing_in = _item(rooms.backlog(run), "Sign in with a college account")

    assert any("cites unknown block B99" in problem for problem in run["problems"])
    (criterion,) = signing_in["criteria"]
    assert (criterion["origin"], criterion["evidence"]) == ("proposed", [])
    assert [b["code"] for b in signing_in["blockers"]] == ["proposed_criterion"]


def _duplicate_ref(draft: Json) -> None:
    _story(draft, "S4")["ref"] = "S5"


def _unknown_parent(draft: Json) -> None:
    _story(draft, "S4")["parent_ref"] = "E7"


def _story_under_a_story(draft: Json) -> None:
    _story(draft, "S4")["parent_ref"] = "S1"


def _nine_stories(draft: Json) -> None:
    draft["items"] += [_story(DRAFT, "S5") | {"ref": f"S{n}"} for n in range(6, 10)]


@pytest.mark.parametrize(
    "break_draft", [_duplicate_ref, _unknown_parent, _story_under_a_story, _nine_stories]
)
def test_broken_ids_hierarchy_or_limits_are_repaired_once_or_the_run_fails(
    rooms: RoomBooking, break_draft: Callable[[Json], None]
) -> None:
    broken = _edited(break_draft)

    repaired = rooms.review(broken, repair=DRAFT)
    failed = rooms.review(broken, repair=broken)

    assert repaired["status"] == "ready_for_review"
    assert len(rooms.backlog(repaired)["items"]) == 7
    assert (failed["status"], failed["error"]["code"]) == ("failed", "INVALID_MODEL_OUTPUT")
    assert failed["candidate_version_id"] is None
    assert failed["usage"]["model_turns"] == 4, "one repair, never a loop"


def test_excluded_work_the_model_still_drafts_is_blocked(rooms: RoomBooking) -> None:
    def add_recurring(draft: Json) -> None:
        _story(draft, "S5")["covers"].append("T6")

    run = rooms.review(_edited(add_recurring), repair=NO_CHANGES)
    backlog = rooms.backlog(run)

    assert any("covers exclusion statement T6" in problem for problem in run["problems"])
    blocked = _decision(backlog, "Recurring reservations are out of scope for release one.")
    story = _item(backlog, "See who booked each room")
    assert (blocked["kind"], blocked["status"]) == ("conflict", "open")
    assert blocked["affected_item_ids"] == [story["id"]]
    assert "unresolved_conflict" in {b["code"] for b in story["blockers"]}


def test_the_candidate_and_the_answers_survive_a_restart(
    rooms: RoomBooking, make_client: Callable[[str], TestClient]
) -> None:
    run = rooms.review()
    before = rooms.backlog(run)

    restarted = make_client(rooms.database_url)
    run_after = restarted.get(f"/api/v1/runs/{run['id']}").json()
    after = restarted.get(
        f"/api/v1/projects/{DEMO_PROJECT_ID}/backlogs/{run['candidate_version_id']}"
    ).json()

    assert after == before
    assert run_after["candidate_version_id"] == run["candidate_version_id"]
    assert run_after["source_version_ids"] == rooms.source_version_ids
    cancellation, length = run_after["questions"]
    assert (cancellation["status"], cancellation["answer"]) == ("answered", CANCEL_ANSWER)
    assert (length["status"], length["answer"]) == ("skipped", None)
    for question in (cancellation, length):
        assert question["answered_by"] == str(LOCAL_REVIEWER_ID)
        assert datetime.fromisoformat(question["answered_at"]).tzinfo is not None
        assert [e["block_id"] for e in question["evidence"]] == question["evidence_block_ids"]
        assert {e["source_version_id"] for e in question["evidence"]} <= set(
            rooms.source_version_ids
        )
        assert len(question["evidence"]) == 2


def test_a_finished_run_keeps_its_one_candidate(rooms: RoomBooking) -> None:
    run = rooms.review()

    again = rooms.post(f"/runs/{run['id']}/advance")

    assert again["candidate_version_id"] == run["candidate_version_id"]
    with rooms.session() as session:
        assert session.scalar(select(func.count()).select_from(VersionRecord)) == 1


def test_a_backlog_version_is_visible_only_inside_its_project(rooms: RoomBooking) -> None:
    version_id = rooms.review()["candidate_version_id"]
    other_project = _other_project(rooms)

    elsewhere = rooms.client.get(f"/api/v1/projects/{other_project}/backlogs/{version_id}")
    unknown = rooms.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/backlogs/{new_id()}")
    outsider = rooms.client.get(f"/api/v1/projects/{new_id()}/backlogs/{version_id}")

    assert [r.status_code for r in (elsewhere, unknown, outsider)] == [404, 404, 404]
    assert elsewhere.json()["message"] == "Backlog version not found"


@pytest.mark.parametrize(("length", "status"), [(2000, 200), (2001, 422)])
def test_an_answer_may_be_at_most_2000_characters(
    rooms: RoomBooking, length: int, status: int
) -> None:
    ask = _result(calls=(ToolCall("call-1", "request_clarification", CLARIFICATION),))
    rooms.script([ask])
    run = rooms.post(
        f"/projects/{DEMO_PROJECT_ID}/runs",
        {"mode": "initial", "source_version_ids": rooms.source_version_ids},
    )
    question = rooms.post(f"/runs/{run['id']}/advance")["questions"][0]

    response = rooms.client.post(
        f"/api/v1/runs/{run['id']}/answers",
        json={"question_id": question["id"], "answer": "x" * length},
        headers={"Idempotency-Key": rooms.key()},
    )

    assert response.status_code == status
    saved = rooms.get(f"/runs/{run['id']}")["questions"][0]
    assert saved["status"] == ("answered" if status == 200 else "open")


def test_a_candidate_citing_another_projects_source_is_refused(rooms: RoomBooking) -> None:
    other_project = _other_project(rooms)
    foreign_version = rooms.upload(other_project)[0]
    foreign_block = rooms.client.get(
        f"/api/v1/projects/{other_project}/sources/{foreign_version}/blocks"
    ).json()[7]
    stolen = Evidence(
        UUID(foreign_version), UUID(foreign_block["id"]), "book an individual one-off slot"
    )
    proposal = CandidateProposal(
        project_id=DEMO_PROJECT_ID,
        run_id=new_id(),
        created_by=LOCAL_REVIEWER_ID,
        source_version_ids=(UUID(foreign_version),),
        items=(
            ProposedItem("E1", "epic", None, "Booking", "Booking rooms."),
            ProposedItem(
                "S1",
                "story",
                "E1",
                "Book a room",
                "As a student, I want to book a room, so that I can study.",
                criteria=(
                    ProposedCriterion("A user can book.", proposed=False, evidence=(stolen,)),
                ),
            ),
        ),
    )

    with rooms.session() as session:
        problems = candidate_problems(session, proposal)
        with pytest.raises(CandidateRejectedError):
            save_candidate(session, proposal, utc_now())
        session.commit()
        saved = session.scalar(select(func.count()).select_from(VersionRecord))

    assert problems == [f"source version {foreign_version} is not in this project"]
    assert saved == 0


def test_a_candidate_the_backlog_refuses_fails_the_run_and_saves_nothing(
    rooms: RoomBooking, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Refusing(SqlCandidateStore):
        def problems(self, proposal: CandidateProposal) -> list[str]:
            return ["block 0000 is not a paragraph of source version 0000"]

    monkeypatch.setattr(agent_router, "SqlCandidateStore", Refusing)

    run = rooms.review()

    assert (run["status"], run["error"]["code"]) == ("failed", "CANDIDATE_REFUSED")
    assert run["error"]["retryable"] is False
    assert run["problems"] == ["block 0000 is not a paragraph of source version 0000"]
    assert run["candidate_version_id"] is None
    with rooms.session() as session:
        assert session.scalar(select(func.count()).select_from(VersionRecord)) == 0
    feed = rooms.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/activity").json()
    assert "backlog.draft_saved" not in {event["type"] for event in feed["events"]}


def _other_project(rooms: RoomBooking) -> ProjectId:
    project_id = ProjectId(new_id())
    with rooms.session() as session:
        SqlProjectRepository(session).add(
            Project(id=project_id, name="Makerspace Tool Library", created_at=utc_now())
        )
        session.flush()
        SqlUserRepository(session).add_membership(
            Membership(
                user_id=LOCAL_REVIEWER_ID,
                project_id=project_id,
                role=Role.EDITOR,
                granted_at=utc_now(),
            )
        )
        session.commit()
    return project_id
