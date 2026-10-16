"""Change requests end to end through the API, with a scripted provider: no live model calls.

A request is recorded against the approved baseline, a change run analyses it, and a candidate
in review is saved beside the baseline, which never changes. The project and its baseline are
synthetic: a room-booking backlog that excludes recurring bookings.
"""

import json
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scopesteps.agent.client import ModelProviderError, RunLimits
from scopesteps.agent.domain.model import ModelResult, ModelTurn, ToolCall, Usage
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID
from scopesteps.backlog.client import (
    BacklogVersionId,
    CandidateProposal,
    Evidence,
    ProposedCriterion,
    ProposedItem,
    ScopeNote,
    save_candidate,
)
from scopesteps.backlog.infrastructure.orm import VersionRecord
from scopesteps.change_control.application.decisions import ChangeOutcome, ScopeDecision
from scopesteps.change_control.client import get_change_outcome_recorder
from scopesteps.change_control.http import router as change_control_router
from scopesteps.change_control.infrastructure.orm import ApprovalRecord
from scopesteps.change_control.infrastructure.repository import SqlDecisionStore
from scopesteps.identity.client import Role
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

Json = dict[str, Any]
MODEL = "gemini-3.5-flash-lite"
LIMITS = RunLimits(
    max_turns=6, max_tool_calls=8, max_output_tokens_per_call=8000, max_total_tokens=200_000
)
BRIEF = (
    b"# Room booking\n\nStudents book study rooms one slot at a time.\n\n"
    b"Recurring bookings are out of scope for release one.\n\n"
    b"Students see which rooms are free."
)
TRANSCRIPT = b"**Dana:** Bookings may be cancelled up to an hour before.\n\n**Lee:** Agreed."
REQUEST = "Student societies want weekly recurring bookings, for example every Tuesday evening."
# Blocks as a change run numbers them: the baseline's sources, then the request.
B_BOOK, B_EXCLUDED, B_FREE, B_CANCEL, B_REQUEST = "B2", "B3", "B4", "B5", "B7"
ANSWER = "A single week or the whole series can be cancelled."


def _result(text: str | None = None, calls: tuple[ToolCall, ...] = ()) -> ModelResult:
    return ModelResult(
        provider="test",
        model_id=MODEL,
        turn=ModelTurn(({"type": "model_output", "text": text or ""},)),
        text=text,
        tool_calls=calls,
        finish_reason="tool_calls" if calls else "completed",
        usage=Usage(input_tokens=1000, output_tokens=100, total_tokens=1100),
        latency_ms=50,
    )


READY = _result("READY")


def _ask() -> ModelResult:
    question = {
        "subject": "Cancelling a series",
        "question": "Can one week of a series be cancelled, or only the whole series?",
        "why_it_matters": "The cancellation story needs a rule for series.",
        "block_ids": [B_REQUEST],
    }
    return _result(calls=(ToolCall("call-1", "request_clarification", {"questions": [question]}),))


def _cite(block: str, quote: str) -> Json:
    return {"block_id": block, "quote": quote}


def _op(op: str, item: str, **fields: Any) -> Json:
    return {
        "op": op,
        "item": item,
        "kind": None,
        "parent": None,
        "title": None,
        "description": None,
        "add_criteria": [],
        "change_criteria": [],
        "remove_criteria": [],
        "rationale": "The request asks for it.",
        "citations": [_cite(B_REQUEST, "weekly recurring bookings")],
        "needs_decision": [],
    } | fields


SERIES = _op(
    "add_item",
    "N1",
    kind="story",
    parent="E1",
    title="Book a weekly series",
    description="As a society, I want to book a room every week, so that we can meet.",
    add_criteria=[
        {
            "text": "A student books the same slot every week.",
            "origin": "source",
            "citations": [_cite(B_REQUEST, "weekly recurring bookings")],
        }
    ],
    citations=[
        _cite(B_REQUEST, "weekly recurring bookings"),
        _cite(B_EXCLUDED, "Recurring bookings are out of scope"),
    ],
    needs_decision=["R1"],
)
CANCEL_ONE_WEEK = _op(
    "modify_item",
    "S2",
    add_criteria=[
        {
            "text": "A single week of a series can be cancelled.",
            "origin": "source",
            "citations": [_cite("A1", ANSWER)],
        }
    ],
    citations=[_cite("A1", ANSWER)],
    needs_decision=["R1"],
)
CANCEL_SAFE = _op(
    "modify_item",
    "S2",
    title="Cancel a booking or a series",
    citations=[_cite(B_REQUEST, "weekly recurring bookings")],
)

REVERSAL = {
    "ref": "R1",
    "reverses": "X1",
    "question": "Reverse the exclusion of recurring bookings for the next release?",
    "why_it_matters": "Release one excluded them.",
    "citations": [_cite(B_REQUEST, "weekly recurring bookings")],
}


def _change_set(**fields: Any) -> ModelResult:
    body: Json = {
        "outcome": "change",
        "summary": "Adds weekly recurring bookings, which the baseline excluded.",
        "summary_citations": [_cite(B_REQUEST, "weekly recurring bookings")],
        "covered_by": [],
        "operations": [SERIES, CANCEL_ONE_WEEK],
        "scope_decisions": [REVERSAL],
        "questions": [],
        "impacts": [
            {
                "item": "S1",
                "note": "A single booking must not clash with a series.",
                "citations": [_cite(B_BOOK, "Students book study rooms")],
            }
        ],
    } | fields
    return _result(json.dumps(body))


NO_CHANGE = _change_set(
    outcome="no_change_needed",
    summary="The baseline already lets students see free rooms.",
    summary_citations=[_cite(B_FREE, "Students see which rooms are free.")],
    covered_by=["S3"],
    operations=[],
    scope_decisions=[],
    impacts=[],
)


@contextmanager
def _session(database_url: str) -> Generator[Session]:
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        yield session
        session.commit()
    engine.dispose()


class Project:
    """The demo project with two sources and an approved baseline v1."""

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
        self.sources = [UUID(v["id"]) for v in response.json()["source_versions"]]
        self.blocks = [self._blocks(version) for version in self.sources]

    def _blocks(self, version: UUID) -> list[UUID]:
        url = f"/api/v1/projects/{DEMO_PROJECT_ID}/sources/{version}/blocks"
        return [UUID(block["id"]) for block in self.client.get(url).json()]

    def approve_baseline(self) -> Json:
        brief, transcript = self.sources

        def cited(source: UUID, block: UUID, quote: str) -> tuple[Evidence, ...]:
            return (Evidence(source, block, quote),)

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
                            "A student books one slot.",
                            proposed=False,
                            evidence=cited(brief, self.blocks[0][1], "Students book study rooms"),
                        ),
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
                            "A booking can be cancelled up to an hour before it starts.",
                            proposed=False,
                            evidence=cited(transcript, self.blocks[1][0], "up to an hour before"),
                        ),
                    ),
                ),
                ProposedItem(
                    "S3",
                    "story",
                    "E1",
                    "See free rooms",
                    "As a student, I want to see free rooms, so that I can choose one.",
                    criteria=(
                        ProposedCriterion(
                            "A student sees which rooms are free.",
                            proposed=False,
                            evidence=cited(brief, self.blocks[0][3], "see which rooms are free"),
                        ),
                    ),
                ),
            ),
            out_of_scope=(
                ScopeNote(
                    "excluded",
                    "Recurring bookings are out of scope for release one.",
                    cited(brief, self.blocks[0][2], "Recurring bookings are out of scope"),
                ),
            ),
        )
        with _session(self.database_url) as session:
            version_id = save_candidate(session, proposal, utc_now())
        draft = self.version(version_id)
        response = self.client.post(
            f"/api/v1/backlogs/{version_id}/approve",
            json={
                "expected_revision": draft["revision"],
                "content_hash": draft["content_hash"],
                "expected_baseline_id": None,
            },
            headers={"Idempotency-Key": self.key()},
        )
        assert response.status_code == 200, response.text
        return self.version(version_id)

    def use(self, provider: Any) -> None:
        self.client.app.state.agent_runtime = replace(  # type: ignore[attr-defined]
            self.client.app.state.agent_runtime,  # type: ignore[attr-defined]
            provider_name="gemini",
            model_id=MODEL,
            limits=LIMITS,
            provider=provider,
        )

    def key(self) -> str:
        self.keys += 1
        return f"change-key-{self.keys:04d}"

    def version(self, version_id: object) -> Json:
        response = self.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/backlogs/{version_id}")
        assert response.status_code == 200, response.text
        return response.json()

    def request(
        self, baseline: Json, text: str = REQUEST, key: str | None = None, **body: Any
    ) -> Response:
        return self.client.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/messages",
            json={
                "text": text,
                "kind": "change_request",
                "base_version_id": baseline["id"],
                "base_content_hash": baseline["content_hash"],
            }
            | body,
            headers={"Idempotency-Key": key or self.key()},
        )

    def advance(self, run_id: str) -> Json:
        response = self.client.post(
            f"/api/v1/runs/{run_id}/advance", headers={"Idempotency-Key": self.key()}
        )
        assert response.status_code == 200, response.text
        return response.json()

    def answer(self, run_id: str, answer: str | None) -> Json:
        run = self.client.get(f"/api/v1/runs/{run_id}").json()
        body = {"question_id": run["questions"][0]["id"]} | (
            {"answer": answer} if answer is not None else {"skip": True}
        )
        response = self.client.post(
            f"/api/v1/runs/{run_id}/answers", json=body, headers={"Idempotency-Key": self.key()}
        )
        assert response.status_code == 200, response.text
        return response.json()

    def analyse(self, baseline: Json, *script: ModelResult | ModelProviderError) -> Json:
        """Send the request and advance its change run until it waits or ends."""
        self.use(ScriptedProvider(script))
        sent = self.request(baseline)
        assert sent.status_code == 202, sent.text
        run = sent.json()["run"]
        while run["status"] in {"created", "running"}:
            run = self.advance(run["id"])
        return run

    def change_requests(self, **params: Any) -> Json:
        response = self.client.get(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/change-requests", params=params
        )
        assert response.status_code == 200, response.text
        return response.json()

    def change_set(self, version_id: str) -> Response:
        return self.client.get(f"/api/v1/backlogs/{version_id}/change-set")

    def thread(self) -> list[Json]:
        messages = self.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/messages").json()
        return list(reversed(messages["messages"]))

    def activity(self, event_type: str) -> list[Json]:
        feed = self.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/activity").json()
        return [event for event in feed["events"] if event["type"] == event_type]

    def versions(self) -> int:
        with _session(self.database_url) as session:
            return session.scalar(select(func.count()).select_from(VersionRecord)) or 0

    def hold_roles(self, *roles: Role) -> None:
        with _session(self.database_url) as session:
            session.query(MembershipRecord).filter(
                MembershipRecord.user_id == LOCAL_REVIEWER_ID,
                MembershipRecord.project_id == DEMO_PROJECT_ID,
            ).delete()
            for role in roles:
                SqlUserRepository(session).add_membership(
                    Membership(
                        user_id=LOCAL_REVIEWER_ID,
                        project_id=ProjectId(DEMO_PROJECT_ID),
                        role=role,
                        granted_at=utc_now(),
                    )
                )


@pytest.fixture
def project(client: TestClient, seeded_database_url: str) -> Project:
    return Project(client, seeded_database_url)


def _error(response: Response, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body: Json = response.json()
    assert body["code"] == code, body
    return body


def _titles(version: Json) -> dict[str, Json]:
    return {item["title"]: item for item in version["items"]}


def test_a_change_request_becomes_a_candidate_beside_an_unchanged_baseline(
    project: Project,
) -> None:
    baseline = project.approve_baseline()
    project.use(ScriptedProvider([_ask(), READY, _change_set()]))

    sent = project.request(baseline)
    assert sent.status_code == 202, sent.text
    run = sent.json()["run"]
    assert (run["mode"], run["status"], run["base_version_id"]) == (
        "change",
        "created",
        baseline["id"],
    )
    assert run["prompt_version"].startswith("change-explore-v1+")
    listed = project.change_requests()["change_requests"]
    assert [(r["number"], r["status"], r["text"]) for r in listed] == [(1, "analyzing", REQUEST)]
    assert listed[0]["id"] == run["change_request_id"]

    asked = project.advance(run["id"])
    assert asked["status"] == "waiting_for_input"
    project.answer(run["id"], ANSWER)
    project.advance(run["id"])
    ready = project.advance(run["id"])

    assert ready["status"] == "ready_for_review", ready
    assert ready["draft"] is None
    candidate = project.version(ready["candidate_version_id"])
    assert (candidate["state"], candidate["base_version_id"]) == ("in_review", baseline["id"])
    assert project.version(baseline["id"]) == baseline, "the baseline never changes"
    before, after = _titles(baseline), _titles(candidate)
    assert after["Book a room"] == before["Book a room"] | {"blockers": []}
    assert after["See free rooms"] == before["See free rooms"] | {"blockers": []}
    assert after["Cancel a booking"]["id"] == before["Cancel a booking"]["id"]
    assert candidate["out_of_scope"] == [], "the exclusion is taken back if the decision says so"


def test_the_change_set_reports_stable_id_operations_and_the_scope_decision(
    project: Project,
) -> None:
    baseline = project.approve_baseline()
    project.use(ScriptedProvider([_ask(), READY, _change_set()]))
    run_id = project.request(baseline).json()["run"]["id"]
    project.advance(run_id)
    project.answer(run_id, ANSWER)
    project.advance(run_id)
    candidate_id = project.advance(run_id)["candidate_version_id"]

    response = project.change_set(candidate_id)

    assert response.status_code == 200, response.text
    change_set = response.json()
    by_id = {item["id"]: item["title"] for item in project.version(candidate_id)["items"]}
    operations = [(op["kind"], by_id[op["item_id"]]) for op in change_set["operations"]]
    assert operations == [
        ("modify_item", "Cancel a booking"),
        ("add_item", "Book a weekly series"),
    ]
    modified = change_set["operations"][0]
    assert modified["changed_fields"] == []
    assert [c["kind"] for c in modified["criteria"]] == ["added"]
    assert modified["rationale"] == "The request asks for it."
    (removed,) = change_set["removed_exclusions"]
    assert removed["summary"] == "Recurring bookings are out of scope for release one."
    (scope,) = change_set["scope_decisions"]
    assert scope["reverses"] == "exclusion"
    decision = next(
        d for d in project.version(candidate_id)["decisions"] if d["id"] == scope["decision_id"]
    )
    assert (decision["kind"], decision["status"]) == ("scope_reversal", "open")
    original = removed["evidence"][0]
    assert {k: decision["evidence"][0][k] for k in original} == original, "cites the exclusion"
    assert any(e["relationship"] == "conflicting" for e in decision["evidence"])
    assert scope["decision_id"] in change_set["open_decision_ids"]
    (impact,) = change_set["impacts"]
    assert by_id[impact["item_id"]] == "Book a room"
    blocked = {b["item_id"] for b in project.version(candidate_id)["blockers"]}
    assert {by_id[i] for i in blocked if i} == {"Cancel a booking", "Book a weekly series"}


def test_the_request_is_recorded_as_evidence_before_analysis(project: Project) -> None:
    baseline = project.approve_baseline()
    project.use(ScriptedProvider([]))

    run = project.request(baseline).json()["run"]

    (request,) = project.change_requests()["change_requests"]
    assert request["base_version_id"] == baseline["id"]
    assert request["base_content_hash"] == baseline["content_hash"]
    assert request["base_version_number"] == 1
    assert request["requested_by"]["user_id"] == str(LOCAL_REVIEWER_ID)
    assert request["source_version_id"] in run["source_version_ids"]
    blocks = project.client.get(
        f"/api/v1/projects/{DEMO_PROJECT_ID}/sources/{request['source_version_id']}/blocks"
    ).json()
    assert [b["text"] for b in blocks] == [REQUEST]
    listed = project.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/sources").json()
    assert request["source_version_id"] not in {v["id"] for v in listed["source_versions"]}
    assert [m["kind"] for m in project.thread()][-1] == "change_request"
    (event,) = project.activity("change.requested")
    assert event["summary"] == "Requested change CR-1 against baseline v1"


def test_the_thread_and_activity_show_the_analysis(project: Project) -> None:
    baseline = project.approve_baseline()
    project.analyse(baseline, READY, _change_set(scope_decisions=[], operations=[CANCEL_SAFE]))

    kinds = [m["event"] or m["kind"] for m in project.thread()]

    assert kinds[-3:] == ["change_request", "analysis", "change.ready_for_review"]
    analysis = project.thread()[-2]
    assert analysis["claims"][0]["basis"] == "cited"
    (event,) = project.activity("change.analyzed")
    assert event["actor"]["kind"] == "agent"
    assert event["summary"] == (
        "Proposed a change: 0 added, 1 changed, 0 removed, 0 scope decisions needed"
    )
    (request,) = project.change_requests()["change_requests"]
    assert request["status"] == "in_review"
    assert request["summary"] == {"added": 0, "changed": 1, "removed": 0}


def test_the_analysis_names_items_instead_of_the_labels_the_model_saw(project: Project) -> None:
    baseline = project.approve_baseline()
    impact = {
        "item": "S1",
        "note": "S1 must not clash with N1.",
        "citations": [_cite(B_BOOK, "Students book study rooms")],
    }
    project.use(ScriptedProvider([_ask(), READY, _change_set(impacts=[impact])]))
    run = project.request(baseline).json()["run"]
    project.advance(run["id"])
    project.answer(run["id"], ANSWER)
    project.advance(run["id"])
    assert project.advance(run["id"])["status"] == "ready_for_review"

    texts = [claim["text"] for claim in project.thread()[-2]["claims"]]

    assert f'Book a room: "Book a room" must not clash with "{SERIES["title"]}".' in texts


def test_a_request_the_baseline_covers_ends_with_no_change_needed(project: Project) -> None:
    baseline = project.approve_baseline()
    versions = project.versions()

    run = project.analyse(baseline, READY, NO_CHANGE)

    assert (run["status"], run["candidate_version_id"]) == ("completed", None)
    assert project.versions() == versions
    (request,) = project.change_requests()["change_requests"]
    assert (request["status"], request["candidate_version_id"], request["summary"]) == (
        "no_change_needed",
        None,
        None,
    )
    assert [m["event"] or m["kind"] for m in project.thread()][-1] == "change.no_change_needed"


@pytest.mark.parametrize(
    ("first", "problem"),
    [
        (_change_set(operations=[_op("modify_item", "S9", title="Gone")]), "S9 is not an item"),
        (
            _change_set(
                scope_decisions=[],
                operations=[
                    _op("modify_item", label, title=f"Rewritten {label}")
                    for label in ("S1", "S2", "S3")
                ],
            ),
            "modifies or removes 3 of 3 stories",
        ),
        (
            _change_set(
                scope_decisions=[],
                operations=[{**SERIES, "needs_decision": []}],
            ),
            "add a scope decision reversing X1",
        ),
        (
            _change_set(
                scope_decisions=[],
                operations=[_op("modify_item", "S1", citations=[_cite(B_BOOK, "Students")])],
            ),
            "cites neither the change request nor a reviewer answer",
        ),
    ],
)
def test_an_invalid_change_set_is_repaired_once_then_refused(
    project: Project, first: ModelResult, problem: str
) -> None:
    baseline = project.approve_baseline()
    versions = project.versions()
    provider = ScriptedProvider([READY, first, first])
    project.use(provider)

    run_id = project.request(baseline).json()["run"]["id"]
    project.advance(run_id)
    run = project.advance(run_id)

    assert run["status"] == "failed"
    assert run["error"]["code"] == "CHANGE_REJECTED"
    assert any(problem in p for p in run["problems"]), run["problems"]
    repair = provider.requests[-1].history[-1]
    assert problem in getattr(repair, "text", "")
    assert project.versions() == versions, "nothing is proposed"
    assert project.version(baseline["id"]) == baseline
    (request,) = project.change_requests()["change_requests"]
    assert (request["status"], request["failure"]) == ("failed", "CHANGE_REJECTED")


def test_a_reversal_the_repair_adds_becomes_a_required_scope_decision(project: Project) -> None:
    baseline = project.approve_baseline()
    unrecorded = _change_set(scope_decisions=[], operations=[{**SERIES, "needs_decision": []}])
    repaired = _change_set(operations=[SERIES])

    run = project.analyse(baseline, READY, unrecorded, repaired)

    assert run["status"] == "ready_for_review"
    candidate = project.version(run["candidate_version_id"])
    (scope,) = [d for d in candidate["decisions"] if d["kind"] == "scope_reversal"]
    assert scope["subject"] == "Reverse: Recurring bookings are out of scope for release one."
    assert any(b["code"] == "scope_decision" for b in candidate["blockers"])


def test_a_skipped_clarification_stays_open_on_the_candidate(project: Project) -> None:
    baseline = project.approve_baseline()
    project.use(ScriptedProvider([_ask(), READY, _change_set(operations=[SERIES])]))
    run_id = project.request(baseline).json()["run"]["id"]
    project.advance(run_id)

    project.answer(run_id, None)
    project.advance(run_id)
    ready = project.advance(run_id)

    candidate = project.version(ready["candidate_version_id"])
    (skipped,) = [d for d in candidate["decisions"] if d["status"] == "skipped"]
    assert skipped["subject"] == "Cancelling a series"
    assert any(b["decision_id"] == skipped["id"] for b in candidate["blockers"])


def test_retrying_and_failing_never_change_the_baseline(project: Project) -> None:
    baseline = project.approve_baseline()
    busy = ModelProviderError("unavailable", "Overloaded", status_code=503)
    denied = ModelProviderError("invalid_request", "Refused", status_code=400)
    project.use(ScriptedProvider([READY, busy, denied]))
    run_id = project.request(baseline).json()["run"]["id"]
    project.advance(run_id)

    retrying = project.advance(run_id)
    assert (retrying["status"], retrying["error"]["retryable"]) == ("running", True)
    assert project.change_requests()["change_requests"][0]["status"] == "analyzing"
    failed = project.advance(run_id)

    assert failed["status"] == "failed"
    assert project.version(baseline["id"]) == baseline
    (request,) = project.change_requests()["change_requests"]
    assert request["status"] == "failed"


def test_stopping_the_analysis_fails_the_request_and_frees_the_project(project: Project) -> None:
    baseline = project.approve_baseline()
    project.use(ScriptedProvider([]))
    run_id = project.request(baseline).json()["run"]["id"]

    stopped = project.client.post(
        f"/api/v1/runs/{run_id}/cancel", headers={"Idempotency-Key": project.key()}
    )

    assert stopped.json()["status"] == "cancelled"
    (request,) = project.change_requests()["change_requests"]
    assert (request["status"], request["failure"]) == ("failed", "RUN_CANCELLED")
    assert project.request(baseline, text="Add a waiting list.").status_code == 202


def test_a_change_request_names_the_current_baseline(project: Project) -> None:
    project.use(ScriptedProvider([]))
    fake = {"id": str(new_id()), "content_hash": "a" * 64}
    _error(project.request(fake), 409, "BASELINE_REQUIRED")
    baseline = project.approve_baseline()

    stale = project.request(baseline | {"content_hash": "b" * 64})
    other = project.request(baseline | {"id": str(new_id())})

    body = _error(stale, 409, "BASELINE_CHANGED")
    assert body["details"]["current_baseline_id"] == baseline["id"]
    _error(other, 409, "BASELINE_CHANGED")
    _error(
        project.client.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/messages",
            json={"text": REQUEST, "kind": "change_request"},
            headers={"Idempotency-Key": project.key()},
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert project.change_requests()["change_requests"] == []


def test_one_change_request_is_analysed_at_a_time(project: Project) -> None:
    baseline = project.approve_baseline()
    project.use(ScriptedProvider([_ask()]))
    run_id = project.request(baseline).json()["run"]["id"]
    project.advance(run_id)

    waiting = project.request(baseline, text="Add a waiting list.")

    body = _error(waiting, 409, "AGENT_BUSY")
    assert body["details"]["run_id"] == run_id
    assert len(project.change_requests()["change_requests"]) == 1


def test_a_retried_request_is_stored_once(project: Project) -> None:
    baseline = project.approve_baseline()
    project.use(ScriptedProvider([]))

    first = project.request(baseline, key="same-key-0001")
    again = project.request(baseline, key="same-key-0001")

    assert first.json()["run"]["id"] == again.json()["run"]["id"]
    assert len(project.change_requests()["change_requests"]) == 1
    _error(
        project.request(baseline, text="Something else.", key="same-key-0001"),
        409,
        "IDEMPOTENCY_KEY_REUSED",
    )


def test_a_change_run_can_be_created_directly(project: Project) -> None:
    baseline = project.approve_baseline()
    project.use(ScriptedProvider([READY, NO_CHANGE]))
    body = {
        "mode": "change",
        "base_version_id": baseline["id"],
        "base_content_hash": baseline["content_hash"],
        "request_text": REQUEST,
    }

    created = project.client.post(
        f"/api/v1/projects/{DEMO_PROJECT_ID}/runs",
        json=body,
        headers={"Idempotency-Key": "create-key-0001"},
    )
    replayed = project.client.post(
        f"/api/v1/projects/{DEMO_PROJECT_ID}/runs",
        json=body,
        headers={"Idempotency-Key": "create-key-0001"},
    )

    assert created.status_code == 202, created.text
    assert replayed.json()["id"] == created.json()["id"]
    assert created.json()["mode"] == "change"
    project.advance(created.json()["id"])
    assert project.advance(created.json()["id"])["status"] == "completed"


def test_a_candidate_in_review_cannot_be_edited(project: Project) -> None:
    baseline = project.approve_baseline()
    run = project.analyse(
        baseline, READY, _change_set(scope_decisions=[], operations=[CANCEL_SAFE])
    )
    candidate = project.version(run["candidate_version_id"])

    edit = project.client.patch(
        f"/api/v1/backlogs/{candidate['id']}/items/{candidate['items'][1]['id']}",
        json={"expected_revision": candidate["revision"], "title": "Edited"},
        headers={"Idempotency-Key": project.key()},
    )

    _error(edit, 409, "VERSION_NOT_DRAFT")


def test_requests_list_newest_first_a_page_at_a_time(project: Project) -> None:
    baseline = project.approve_baseline()
    project.analyse(baseline, READY, NO_CHANGE)
    project.analyse(baseline, READY, NO_CHANGE)

    first = project.change_requests(limit=1)
    second = project.change_requests(limit=1, cursor=first["next_cursor"])

    assert [r["number"] for r in first["change_requests"]] == [2]
    assert [r["number"] for r in second["change_requests"]] == [1]
    assert second["next_cursor"] is None
    _error(
        project.client.get(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/change-requests", params={"cursor": "bad"}
        ),
        422,
        "INVALID_CURSOR",
    )
    one = project.client.get(f"/api/v1/change-requests/{first['change_requests'][0]['id']}")
    assert one.json()["number"] == 2


def test_viewers_read_requests_but_cannot_send_and_outsiders_see_nothing(
    project: Project,
) -> None:
    baseline = project.approve_baseline()
    project.analyse(baseline, READY, NO_CHANGE)
    request_id = project.change_requests()["change_requests"][0]["id"]
    project.hold_roles(Role.VIEWER)

    assert len(project.change_requests()["change_requests"]) == 1
    _error(project.request(baseline), 403, "PERMISSION_DENIED")
    project.hold_roles()
    _error(
        project.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/change-requests"),
        404,
        "NOT_FOUND",
    )
    _error(project.client.get(f"/api/v1/change-requests/{request_id}"), 404, "NOT_FOUND")


def test_a_version_no_request_proposed_has_no_change_set(project: Project) -> None:
    baseline = project.approve_baseline()

    _error(project.change_set(baseline["id"]), 404, "NOT_FOUND")


# Deciding a change candidate: scope decisions, approval as v2, rejection.


def _candidate(project: Project, baseline: Json) -> Json:
    """A candidate that adds a weekly series, reversing the exclusion of recurring bookings."""
    project.use(ScriptedProvider([_ask(), READY, _change_set()]))
    run_id = project.request(baseline).json()["run"]["id"]
    project.advance(run_id)
    project.answer(run_id, ANSWER)
    project.advance(run_id)
    return project.version(project.advance(run_id)["candidate_version_id"])


def _scope_id(candidate: Json) -> str:
    (scope,) = [d for d in candidate["decisions"] if d["kind"] == "scope_reversal"]
    return str(scope["id"])


def _record(project: Project, candidate: Json, outcome: str, key: str | None = None) -> Response:
    return project.client.post(
        f"/api/v1/backlogs/{candidate['id']}/scope-decisions/{_scope_id(candidate)}",
        json={"expected_revision": candidate["revision"], "outcome": outcome},
        headers={"Idempotency-Key": key or project.key()},
    )


def _approve(project: Project, version: Json, baseline_id: str, key: str | None = None) -> Response:
    return project.client.post(
        f"/api/v1/backlogs/{version['id']}/approve",
        json={
            "expected_revision": version["revision"],
            "content_hash": version["content_hash"],
            "expected_baseline_id": baseline_id,
        },
        headers={"Idempotency-Key": key or project.key()},
    )


def _reject(project: Project, version: Json) -> Response:
    return project.client.post(
        f"/api/v1/backlogs/{version['id']}/reject",
        json={"expected_revision": version["revision"], "reason": "Not this release."},
        headers={"Idempotency-Key": project.key()},
    )


def _review(project: Project, version: Json) -> Json:
    response = project.client.post(
        f"/api/v1/backlogs/{version['id']}/review",
        json={"expected_revision": version["revision"]},
        headers={"Idempotency-Key": project.key()},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _reversed(project: Project, candidate: Json) -> Json:
    response = _record(project, candidate, "reverse")
    assert response.status_code == 200, response.text
    return response.json()


def _status(project: Project) -> Json:
    response = project.client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}")
    assert response.status_code == 200, response.text
    return response.json()["status"]


def _approvals(project: Project) -> int:
    with _session(project.database_url) as session:
        return session.scalar(select(func.count()).select_from(ApprovalRecord)) or 0


def test_an_approved_change_becomes_v2_and_v1_stays_as_it_was(project: Project) -> None:
    baseline = project.approve_baseline()
    candidate = _reversed(project, _candidate(project, baseline))

    response = _approve(project, candidate, baseline["id"])

    assert response.status_code == 200, response.text
    decision = response.json()
    assert (decision["decision"], decision["baseline_version"]) == ("approved", 2)
    assert decision["current_baseline_id"] == candidate["id"]
    assert decision["change_request_status"] == "approved"
    v2 = project.version(candidate["id"])
    assert v2["state"] == "approved"
    assert {k: v2[k] for k in ("items", "decisions", "content_hash")} == {
        k: candidate[k] for k in ("items", "decisions", "content_hash")
    }, "v2 is exactly the reviewed candidate"
    assert project.version(baseline["id"]) == baseline, "v1 never changes"
    before, after = _titles(baseline), _titles(v2)
    assert after["Book a room"] == before["Book a room"]
    assert after["See free rooms"] == before["See free rooms"]
    assert "Book a weekly series" in after
    assert (_status(project)["baseline_version"], _status(project)["baseline_version_id"]) == (
        2,
        candidate["id"],
    )
    (request,) = project.change_requests()["change_requests"]
    assert (request["id"], request["status"]) == (decision["change_request_id"], "approved")
    (event,) = project.activity("change.approved")
    assert event["summary"] == (
        "Approved CR-1 as baseline v2 from candidate revision 2 (1 added, 1 changed, 0 removed), "
        "with 1 epic and 4 stories"
    )
    assert event["actor"]["kind"] == "user"
    assert project.activity("backlog.approved") != [], "v1's approval"


def test_a_candidate_is_ready_to_approve_once_its_scope_decision_is_made(project: Project) -> None:
    baseline = project.approve_baseline()
    candidate = _candidate(project, baseline)
    assert _review(project, candidate)["ready"] is False, "the scope decision is still open"

    reversed_ = _reversed(project, candidate)

    review = _review(project, reversed_)
    assert all(check["passed"] for check in review["checks"]), review
    assert review["ready"] is True, "the approve button follows this flag"


def test_a_scope_decision_is_recorded_by_an_approver_with_who_and_when(project: Project) -> None:
    baseline = project.approve_baseline()
    candidate = _candidate(project, baseline)

    after = _reversed(project, candidate)

    scope = next(d for d in after["decisions"] if d["id"] == _scope_id(candidate))
    assert (scope["status"], scope["answer"]) == ("answered", "reverse")
    assert scope["decided_by"] == str(LOCAL_REVIEWER_ID)
    assert scope["decided_at"] is not None
    assert scope["evidence"], "it keeps the evidence of what it reverses"
    assert after["revision"] == candidate["revision"] + 1
    assert after["content_hash"] != candidate["content_hash"]
    assert not any(b["code"] == "scope_decision" for b in after["blockers"])
    (event,) = project.activity("scope.decided")
    assert event["summary"] == "Chose to reverse earlier scope in candidate revision 1"
    assert {"kind": "decision", "id": scope["id"]} in [
        {"kind": s["kind"], "id": s["id"]} for s in event["subjects"]
    ]


def test_a_scope_decision_is_recorded_once(project: Project) -> None:
    baseline = project.approve_baseline()
    candidate = _candidate(project, baseline)

    first = _record(project, candidate, "reverse", key="scope-key-0001")
    replayed = _record(project, candidate, "reverse", key="scope-key-0001")
    stale = _record(project, candidate, "keep")
    again = _record(project, first.json(), "keep")

    assert replayed.status_code == 200
    assert replayed.json()["revision"] == first.json()["revision"]
    _error(stale, 409, "VERSION_CHANGED")
    _error(again, 409, "DECISION_ALREADY_ANSWERED")
    assert len(project.activity("scope.decided")) == 1


def test_approval_waits_for_every_scope_decision(project: Project) -> None:
    baseline = project.approve_baseline()
    candidate = _candidate(project, baseline)

    response = _approve(project, candidate, baseline["id"])

    body = _error(response, 409, "SCOPE_DECISION_REQUIRED")
    assert body["details"]["decision_ids"] == [_scope_id(candidate)]
    assert project.version(candidate["id"]) == candidate
    assert project.change_requests()["change_requests"][0]["status"] == "in_review"


def test_kept_scope_allows_only_rejection_and_the_baseline_stays(project: Project) -> None:
    baseline = project.approve_baseline()
    kept = _record(project, _candidate(project, baseline), "keep").json()

    refused = _approve(project, kept, baseline["id"])
    rejected = _reject(project, kept)

    _error(refused, 409, "SCOPE_KEPT")
    assert rejected.status_code == 200, rejected.text
    decision = rejected.json()
    assert (decision["decision"], decision["baseline_version"]) == ("rejected", None)
    assert decision["current_baseline_id"] == baseline["id"]
    assert decision["change_request_status"] == "rejected"
    assert project.version(kept["id"])["state"] == "rejected"
    assert project.version(baseline["id"]) == baseline
    assert _status(project)["baseline_version_id"] == baseline["id"]
    assert project.change_requests()["change_requests"][0]["status"] == "rejected"
    (event,) = project.activity("change.rejected")
    assert event["summary"] == "Rejected CR-1 at candidate revision 2; the baseline is unchanged"
    assert "Not this release" not in event["summary"]


def test_a_change_can_be_rejected_before_any_scope_decision(project: Project) -> None:
    baseline = project.approve_baseline()
    candidate = _candidate(project, baseline)

    response = _reject(project, candidate)

    assert response.status_code == 200, response.text
    assert _status(project)["baseline_version_id"] == baseline["id"]


@pytest.mark.parametrize("roles", [(Role.EDITOR,), (Role.VIEWER,)])
def test_only_an_approver_records_scope_or_decides_a_change(
    project: Project, roles: tuple[Role, ...]
) -> None:
    baseline = project.approve_baseline()
    candidate = _candidate(project, baseline)
    project.hold_roles(*roles)

    _error(_record(project, candidate, "reverse"), 403, "PERMISSION_DENIED")
    _error(_approve(project, candidate, baseline["id"]), 403, "PERMISSION_DENIED")
    _error(_reject(project, candidate), 403, "PERMISSION_DENIED")
    assert project.version(candidate["id"]) == candidate
    assert project.change_requests()["change_requests"][0]["status"] == "in_review"


def test_the_agent_cannot_record_a_scope_decision(project: Project) -> None:
    baseline = project.approve_baseline()
    candidate = _candidate(project, baseline)

    scope = next(d for d in candidate["decisions"] if d["id"] == _scope_id(candidate))
    assert scope["status"] == "open", "the change run leaves it to an approver"
    assert project.activity("scope.decided") == []
    draft_route = project.client.patch(
        f"/api/v1/backlogs/{candidate['id']}/decisions/{scope['id']}",
        json={"expected_revision": candidate["revision"], "answer": "reverse"},
        headers={"Idempotency-Key": project.key()},
    )
    _error(draft_route, 409, "VERSION_NOT_DRAFT")


def test_stale_or_repeated_approvals_create_no_extra_version(project: Project) -> None:
    baseline = project.approve_baseline()
    candidate = _candidate(project, baseline)
    reversed_ = _reversed(project, candidate)
    versions = project.versions()

    stale = _approve(project, candidate, baseline["id"])
    first = _approve(project, reversed_, baseline["id"], key="approve-change-0001")
    replayed = _approve(project, reversed_, baseline["id"], key="approve-change-0001")
    again = _approve(project, reversed_, baseline["id"])
    rejected_after = _reject(project, reversed_)

    _error(stale, 409, "VERSION_CHANGED")
    assert first.status_code == 200, first.text
    assert replayed.json() == first.json()
    _error(again, 409, "VERSION_NOT_DRAFT")
    _error(rejected_after, 409, "VERSION_NOT_DRAFT")
    assert project.versions() == versions
    assert _approvals(project) == 2
    assert len(project.activity("change.approved")) == 1


def test_a_second_candidate_from_the_old_baseline_cannot_advance_it_again(
    project: Project,
) -> None:
    baseline = project.approve_baseline()
    first = _reversed(project, _candidate(project, baseline))
    second = _reversed(project, _candidate(project, baseline))
    assert _approve(project, first, baseline["id"]).status_code == 200

    stale = _approve(project, second, baseline["id"])
    moved = _approve(project, second, first["id"])

    _error(stale, 409, "BASELINE_CHANGED")
    _error(moved, 409, "BASELINE_CHANGED")
    assert project.version(second["id"]) == second
    assert _status(project)["baseline_version"] == 2


def test_a_concurrent_change_approval_loses_and_stores_nothing(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = project.approve_baseline()
    first = _reversed(project, _candidate(project, baseline))
    second = _reversed(project, _candidate(project, baseline))
    assert _approve(project, first, baseline["id"]).status_code == 200
    v1 = BacklogVersionId(UUID(baseline["id"]))

    class ReadBeforeTheOtherCommitted(SqlDecisionStore):
        def current_baseline(self, project_id: ProjectId) -> ScopeDecision | None:
            # What a request that read the baseline before `first` committed would see.
            return self.of_versions([v1])[v1]

    monkeypatch.setattr(change_control_router, "SqlDecisionStore", ReadBeforeTheOtherCommitted)
    response = _approve(project, second, baseline["id"])

    _error(response, 409, "DECISION_IN_PROGRESS")
    assert project.version(second["id"]) == second
    listed = project.change_requests()["change_requests"]
    assert {r["candidate_version_id"]: r["status"] for r in listed}[second["id"]] == "in_review"
    assert len(project.activity("change.approved")) == 1


def test_a_failed_audit_write_rolls_the_whole_change_approval_back(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = project.approve_baseline()
    candidate = _reversed(project, _candidate(project, baseline))
    approvals = _approvals(project)

    class BrokenRecorder:
        def record(self, **_: object) -> None:
            raise RuntimeError("audit store unavailable")

    def broken_recorder(_session: Session) -> BrokenRecorder:
        return BrokenRecorder()

    monkeypatch.setattr(change_control_router, "audit_recorder", broken_recorder)
    with pytest.raises(RuntimeError, match="audit store unavailable"):
        _approve(project, candidate, baseline["id"])
    with pytest.raises(RuntimeError, match="audit store unavailable"):
        _reject(project, candidate)

    assert project.version(candidate["id"]) == candidate
    assert project.version(baseline["id"]) == baseline
    assert _approvals(project) == approvals
    assert _status(project)["baseline_version_id"] == baseline["id"]
    assert project.change_requests()["change_requests"][0]["status"] == "in_review"
    assert _outcome_events(project) == []


def test_a_failed_conversation_write_rolls_the_whole_change_decision_back(
    project: Project,
) -> None:
    baseline = project.approve_baseline()
    candidate = _reversed(project, _candidate(project, baseline))
    approvals = _approvals(project)

    def broken(_outcome: ChangeOutcome) -> None:
        raise RuntimeError("conversation store unavailable")

    overrides = project.client.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[get_change_outcome_recorder] = lambda: broken
    with pytest.raises(RuntimeError, match="conversation store unavailable"):
        _approve(project, candidate, baseline["id"])
    with pytest.raises(RuntimeError, match="conversation store unavailable"):
        _reject(project, candidate)

    assert project.version(candidate["id"]) == candidate
    assert _approvals(project) == approvals
    assert _status(project)["baseline_version_id"] == baseline["id"]
    assert project.change_requests()["change_requests"][0]["status"] == "in_review"
    assert project.activity("change.approved") == []
    assert project.activity("change.rejected") == []
    assert _outcome_events(project) == []


def _outcome_events(project: Project) -> list[Json]:
    return [m for m in project.thread() if m["event"] in {"change.approved", "change.rejected"}]


def test_an_approved_change_is_posted_to_the_thread_with_its_baseline(project: Project) -> None:
    baseline = project.approve_baseline()
    candidate = _reversed(project, _candidate(project, baseline))

    decision = _approve(project, candidate, baseline["id"]).json()

    (event,) = _outcome_events(project)
    assert event == project.thread()[-1], "the newest message"
    assert (event["kind"], event["role"], event["event"]) == ("event", "system", "change.approved")
    assert event["change_request_id"] == decision["change_request_id"]
    assert event["baseline_version"] == 2
    assert event["text"] == "CR-1 was approved as baseline v2."
    assert event["author"]["user_id"] == str(LOCAL_REVIEWER_ID)
    (request,) = project.change_requests()["change_requests"]
    assert event["run_id"] == request["run_id"]
    assert request["approved_version_number"] == 2
    one = project.client.get(f"/api/v1/change-requests/{request['id']}").json()
    assert one["approved_version_number"] == 2
    assert one["base_version_number"] == 1


def test_a_rejected_change_is_posted_to_the_thread_and_the_baseline_stays(
    project: Project,
) -> None:
    baseline = project.approve_baseline()
    candidate = _candidate(project, baseline)

    decision = _reject(project, candidate).json()

    (event,) = _outcome_events(project)
    assert event["event"] == "change.rejected"
    assert event["change_request_id"] == decision["change_request_id"]
    assert event["baseline_version"] == 1, "the baseline it leaves in place"
    assert event["text"] == "CR-1 was rejected; the baseline stays v1."
    assert "Not this release" not in event["text"], "the reason stays on the decision"
    (request,) = project.change_requests()["change_requests"]
    assert request["status"] == "rejected"
    assert request["approved_version_number"] is None


def test_a_change_waiting_for_a_decision_has_no_outcome_yet(project: Project) -> None:
    baseline = project.approve_baseline()
    _candidate(project, baseline)

    assert _outcome_events(project) == []
    assert project.change_requests()["change_requests"][0]["approved_version_number"] is None


def _skipped_candidate(project: Project, baseline: Json) -> Json:
    """A candidate whose clarification was skipped during the change run, so it stays open."""
    project.use(ScriptedProvider([_ask(), READY, _change_set(operations=[SERIES])]))
    run_id = project.request(baseline).json()["run"]["id"]
    project.advance(run_id)
    project.answer(run_id, None)
    project.advance(run_id)
    return project.version(project.advance(run_id)["candidate_version_id"])


def _skipped_id(candidate: Json) -> str:
    (skipped,) = [d for d in candidate["decisions"] if d["status"] == "skipped"]
    return str(skipped["id"])


def _answer_open(
    project: Project, candidate: Json, decision_id: str, answer: str = ANSWER
) -> Response:
    return project.client.post(
        f"/api/v1/backlogs/{candidate['id']}/candidate-decisions/{decision_id}",
        json={"expected_revision": candidate["revision"], "answer": answer},
        headers={"Idempotency-Key": project.key()},
    )


def test_an_approver_answers_a_skipped_clarification_so_the_change_can_be_approved(
    project: Project,
) -> None:
    baseline = project.approve_baseline()
    candidate = _skipped_candidate(project, baseline)
    skipped_id = _skipped_id(candidate)
    _error(
        _approve(project, _reversed(project, candidate), baseline["id"]), 409, "APPROVAL_BLOCKED"
    )
    reversed_ = project.version(candidate["id"])

    response = _answer_open(project, reversed_, skipped_id)

    assert response.status_code == 200, response.text
    answered = response.json()
    decision = next(d for d in answered["decisions"] if d["id"] == skipped_id)
    assert (decision["status"], decision["answer"]) == ("answered", ANSWER)
    assert decision["decided_by"] == str(LOCAL_REVIEWER_ID)
    assert decision["decided_at"] is not None
    assert answered["revision"] == reversed_["revision"] + 1
    assert answered["content_hash"] != reversed_["content_hash"]
    assert answered["state"] == "in_review"
    assert not any(b["decision_id"] == skipped_id for b in answered["blockers"])
    assert _review(project, answered)["ready"] is True
    summaries = [event["summary"] for event in project.activity("scope.decided")]
    assert f"Answered a skipped missing_decision in candidate revision {reversed_['revision']}" in (
        summaries
    )
    approved = _approve(project, answered, baseline["id"])
    assert approved.status_code == 200, approved.text
    assert approved.json()["baseline_version"] == 2


def test_a_candidate_decision_answer_must_match_the_reviewed_revision(project: Project) -> None:
    baseline = project.approve_baseline()
    candidate = _skipped_candidate(project, baseline)
    reversed_ = _reversed(project, candidate)

    stale = _answer_open(project, candidate, _skipped_id(candidate))
    answered = _answer_open(project, reversed_, _skipped_id(candidate)).json()
    again = _answer_open(project, answered, _skipped_id(candidate), "Something else.")
    stale_approval = _approve(project, reversed_, baseline["id"])

    _error(stale, 409, "VERSION_CHANGED")
    _error(again, 409, "DECISION_ALREADY_ANSWERED")
    _error(stale_approval, 409, "VERSION_CHANGED")
    assert project.version(candidate["id"]) == answered


def test_only_an_approver_answers_open_decisions_on_a_candidate_in_review(
    project: Project,
) -> None:
    baseline = project.approve_baseline()
    candidate = _skipped_candidate(project, baseline)

    scope = _answer_open(project, candidate, _scope_id(candidate), "reverse")
    on_baseline = _answer_open(project, baseline, _scope_id(candidate))
    project.hold_roles(Role.EDITOR)
    editor = _answer_open(project, candidate, _skipped_id(candidate))

    _error(scope, 409, "SCOPE_DECISION_NEEDS_OUTCOME")
    _error(on_baseline, 409, "VERSION_NOT_IN_REVIEW")
    _error(editor, 403, "PERMISSION_DENIED")
    assert project.version(candidate["id"]) == candidate


def test_an_approved_change_survives_a_restart(
    project: Project, make_client: Callable[..., TestClient]
) -> None:
    baseline = project.approve_baseline()
    candidate = _reversed(project, _candidate(project, baseline))
    decision = _approve(project, candidate, baseline["id"]).json()

    restarted = Project.__new__(Project)
    restarted.client = make_client(project.database_url)
    restarted.database_url = project.database_url
    restarted.keys = 100

    assert restarted.version(candidate["id"]) == project.version(candidate["id"])
    assert restarted.version(baseline["id"]) == baseline
    assert _status(restarted)["baseline_version"] == 2
    (request,) = restarted.change_requests()["change_requests"]
    assert request["status"] == "approved"
    scope = next(
        d
        for d in restarted.version(candidate["id"])["decisions"]
        if d["id"] == _scope_id(candidate)
    )
    assert (scope["answer"], scope["decided_by"]) == ("reverse", str(LOCAL_REVIEWER_ID))
    replayed = restarted.client.post(
        f"/api/v1/backlogs/{candidate['id']}/approve",
        json={
            "expected_revision": candidate["revision"],
            "content_hash": candidate["content_hash"],
            "expected_baseline_id": baseline["id"],
        },
        headers={"Idempotency-Key": project.key()},
    )
    _error(replayed, 409, "VERSION_NOT_DRAFT")
    assert decision["baseline_version"] == 2
