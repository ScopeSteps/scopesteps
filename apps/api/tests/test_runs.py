"""Agent runs end to end through the API, with a scripted provider: no live model calls."""

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import select, update

from scopesteps.agent.client import ModelProviderError, ModelRequest, RunLimits, ServedModel
from scopesteps.agent.domain.model import ModelResult, ModelTurn, ToolCall, ToolResults, Usage
from scopesteps.agent.infrastructure.orm import RunRecord, RunStepRecord
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID
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

BRIEF = b"# Room booking\n\nStudents book study rooms.\n\nNo recurring bookings in release one."
TRANSCRIPT = b"**Dana:** Keep it to single slots.\n\n**Lee:** Agreed."
MODEL = "gemini-3.5-flash-lite"
LIMITS = RunLimits(
    max_turns=6, max_tool_calls=8, max_output_tokens_per_call=8000, max_total_tokens=200_000
)
QUOTE = {"block_id": "B2", "quote": "Students book study rooms."}


def _result(
    text: str | None = None, calls: tuple[ToolCall, ...] = (), tokens: int = 1000
) -> ModelResult:
    return ModelResult(
        provider="test",
        model_id=MODEL,
        turn=ModelTurn(({"type": "model_output", "text": text or ""},)),
        text=text,
        tool_calls=calls,
        finish_reason="tool_calls" if calls else "completed",
        usage=Usage(input_tokens=tokens, output_tokens=100, total_tokens=tokens + 100),
        latency_ms=50,
    )


def _ask(*questions: dict[str, Any]) -> ModelResult:
    return _result(calls=(ToolCall("call-1", "request_clarification", {"questions": questions}),))


CANCEL_QUESTION = {
    "subject": "Cancellation",
    "question": "When may students cancel a booking?",
    "why_it_matters": "Cancellation rules are missing.",
    "block_ids": ["B2"],
}
LENGTH_QUESTION = {
    "subject": "Length",
    "question": "How long may one booking be?",
    "why_it_matters": "Slots are not defined.",
    "block_ids": ["B4"],
}
READY = _result("READY")


def _draft(*, answer: str | None = None) -> str:
    criteria: list[dict[str, Any]] = [
        {"text": "A student can book a free room.", "origin": "source", "citations": [QUOTE]}
    ]
    if answer:
        criteria.append(
            {
                "text": "Cancellation follows the reviewer's rule.",
                "origin": "source",
                "citations": [{"block_id": "A1", "quote": answer}],
            }
        )
    return json.dumps(
        {
            "statements": [
                {"id": "T1", "kind": "confirmed", "summary": "Book rooms", "citations": [QUOTE]},
                {
                    "id": "T2",
                    "kind": "exclusion",
                    "summary": "No recurring bookings",
                    "citations": [{"block_id": "B3", "quote": "No recurring bookings"}],
                },
                {
                    "id": "T3",
                    "kind": "context",
                    "summary": "Single slots",
                    "citations": [
                        {"block_id": "B4", "quote": "Keep it to single slots."},
                        {"block_id": "B5", "quote": "Agreed."},
                    ],
                },
            ],
            "items": [
                {
                    "ref": "E1",
                    "kind": "epic",
                    "parent_ref": None,
                    "title": "Booking",
                    "description": "Room booking.",
                    "criteria": [],
                    "assumptions": [],
                    "open_questions": [],
                    "covers": [],
                },
                {
                    "ref": "S1",
                    "kind": "story",
                    "parent_ref": "E1",
                    "title": "Book a room",
                    "description": "As a student, I want to book a room, so that I can study.",
                    "criteria": criteria,
                    "assumptions": [],
                    "open_questions": [],
                    "covers": ["T1"],
                },
            ],
            "questions": [
                {
                    "subject": "Length",
                    "question": "How long may one booking be?",
                    "why_it_matters": "Still open.",
                    "citations": [{"block_id": "U1", "quote": "has not answered this yet"}],
                }
            ],
        }
    )


class Harness:
    def __init__(self, client: TestClient, database_url: str) -> None:
        self.client = client
        self.database_url = database_url
        self.keys = 0
        versions = self.client.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/sources",
            files={"brief": ("brief.md", BRIEF), "transcript": ("transcript.md", TRANSCRIPT)},
            headers={"Idempotency-Key": "upload-key-0001"},
        ).json()["source_versions"]
        self.version_ids = [version["id"] for version in versions]

    def use(self, provider: Any, **changes: Any) -> None:
        self.client.app.state.agent_runtime = replace(  # type: ignore[attr-defined]
            self.client.app.state.agent_runtime,  # type: ignore[attr-defined]
            **({"provider_name": "gemini", "model_id": MODEL, "limits": LIMITS} | changes),
            provider=provider,
        )

    def key(self) -> str:
        self.keys += 1
        return f"request-key-{self.keys:04d}"

    def create(self, key: str | None = None, **body: Any) -> Response:
        return self.client.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/runs",
            json={"mode": "initial", "source_version_ids": self.version_ids} | body,
            headers={"Idempotency-Key": key or self.key()},
        )

    def advance(self, run_id: str, key: str | None = None) -> Response:
        return self.client.post(
            f"/api/v1/runs/{run_id}/advance", headers={"Idempotency-Key": key or self.key()}
        )

    def answer(self, run_id: str, question_id: str, answer: str | None) -> Response:
        body = {"question_id": question_id} | (
            {"answer": answer} if answer is not None else {"skip": True}
        )
        return self.client.post(
            f"/api/v1/runs/{run_id}/answers", json=body, headers={"Idempotency-Key": self.key()}
        )

    def steps(self, run_id: str) -> list[RunStepRecord]:
        engine = create_database_engine(self.database_url)
        with create_session_factory(engine)() as session:
            steps = list(
                session.scalars(
                    select(RunStepRecord)
                    .where(RunStepRecord.run_id == UUID(run_id))
                    .order_by(RunStepRecord.sequence)
                )
            )
        engine.dispose()
        return steps

    def update_run(self, run_id: str, **values: Any) -> None:
        engine = create_database_engine(self.database_url)
        with create_session_factory(engine)() as session:
            session.execute(update(RunRecord).where(RunRecord.id == UUID(run_id)).values(**values))
            session.commit()
        engine.dispose()


@pytest.fixture
def harness(client: TestClient, seeded_database_url: str) -> Harness:
    return Harness(client, seeded_database_url)


def _created(harness: Harness, provider: Any) -> str:
    harness.use(provider)
    response = harness.create()
    assert response.status_code == 202, response.text
    return response.json()["id"]


def test_a_run_clarifies_then_drafts_with_answers_and_open_decisions(harness: Harness) -> None:
    answer = "Up to two hours before the start."
    provider = ScriptedProvider(
        [_ask(CANCEL_QUESTION, LENGTH_QUESTION), READY, _result(_draft(answer=answer))]
    )
    run_id = _created(harness, provider)

    created = harness.client.get(f"/api/v1/runs/{run_id}").json()
    assert (created["status"], created["revision"], created["usage"]["model_turns"]) == (
        "created",
        1,
        0,
    )
    assert created["model_id"] == MODEL
    assert created["prompt_version"].startswith("explore-v1+")

    waiting = harness.advance(run_id).json()
    assert waiting["status"] == "waiting_for_input"
    assert [q["subject"] for q in waiting["questions"]] == ["Cancellation", "Length"]
    assert len(waiting["questions"][0]["evidence_block_ids"]) == 1
    tools = {tool.name for tool in provider.requests[0].tools}
    assert tools == {"lookup_source", "request_clarification"}, "no approval or publish tools"

    still_waiting = harness.answer(run_id, waiting["questions"][0]["id"], answer).json()
    assert still_waiting["status"] == "waiting_for_input"
    resumed = harness.answer(run_id, waiting["questions"][1]["id"], None).json()
    assert resumed["status"] == "running"
    assert resumed["usage"]["model_turns"] == 1, "answering never resets counters"

    harness.advance(run_id)
    answers = provider.requests[1].history[-1]
    assert isinstance(answers, ToolResults)
    assert answers.results[0].name == "request_clarification"
    assert "Up to two hours" in json.dumps(answers.results[0].output)

    ready = harness.advance(run_id).json()
    assert ready["status"] == "ready_for_review", ready
    assert ready["problems"] == []
    assert ready["draft"]["items"][1]["covers"] == ["T1"]
    refs = {ref["label"]: ref for ref in ready["block_refs"]}
    assert refs["A1"]["question_id"] == waiting["questions"][0]["id"]
    assert refs["U1"]["question_id"] == waiting["questions"][1]["id"]
    assert refs["B2"]["source_block_id"] is not None
    assert ready["usage"]["model_turns"] == 3
    assert float(ready["usage"]["cost_usd_estimate"]) > 0
    assert ready["project_usage"]["cost_usd_estimate"] == ready["usage"]["cost_usd_estimate"]

    steps = harness.steps(run_id)
    assert [(s.kind, s.name, s.stage) for s in steps] == [
        ("model_call", "generate", "explore"),
        ("tool", "request_clarification", "explore"),
        ("model_call", "generate", "explore"),
        ("model_call", "generate", "draft"),
        ("tool", "validate_backlog", "draft"),
    ]
    draft_call = steps[3]
    assert draft_call.prompt_version.startswith("draft-v3+")
    assert draft_call.schema_version == "draft-backlog.v2"
    assert (draft_call.input_tokens, draft_call.output_tokens) == (1000, 100)
    assert draft_call.cost_microusd is not None
    assert draft_call.cost_microusd > 0
    assert steps[4].detail == {
        "problems": 0,
        "repair": "none",
        "repaired": False,
        "repair_triggers": [],
    }


def test_the_draft_step_repairs_with_a_patch_and_keeps_remaining_problems(
    harness: Harness,
) -> None:
    broken = json.loads(_draft())
    broken["items"][1]["covers"] = []
    patch: dict[str, list[object]] = {"statements": [], "items": [], "questions": []}
    provider = ScriptedProvider([READY, _result(json.dumps(broken)), _result(json.dumps(patch))])
    run_id = _created(harness, provider)

    harness.advance(run_id)
    ready = harness.advance(run_id).json()

    assert ready["status"] == "ready_for_review"
    assert any("not covered" in problem for problem in ready["problems"])
    calls = [s for s in harness.steps(run_id) if s.kind == "model_call"]
    assert [(s.attempt, s.repair) for s in calls] == [(1, "none"), (1, "none"), (2, "targeted")]


def test_repeating_an_advance_with_the_same_key_runs_no_second_step(harness: Harness) -> None:
    provider = ScriptedProvider([READY])
    run_id = _created(harness, provider)

    first = harness.advance(run_id, key="advance-key-0001").json()
    again = harness.advance(run_id, key="advance-key-0001").json()

    assert first["revision"] == again["revision"]
    assert len(provider.requests) == 1
    assert len(harness.steps(run_id)) == 1


def test_creating_with_a_reused_key_returns_the_same_run_or_409(harness: Harness) -> None:
    harness.use(ScriptedProvider([]))

    first = harness.create(key="create-key-0001").json()
    again = harness.create(key="create-key-0001").json()
    other = harness.create(key="create-key-0001", source_version_ids=harness.version_ids[:1])

    assert first["id"] == again["id"]
    assert other.status_code == 409
    assert other.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_an_active_lease_makes_a_concurrent_advance_wait(harness: Harness) -> None:
    run_id = _created(harness, ScriptedProvider([READY]))
    harness.update_run(run_id, lease_token=new_id(), lease_expires_at=utc_now() + timedelta(60))

    response = harness.advance(run_id)

    assert response.status_code == 409
    assert response.json()["code"] == "RUN_BUSY"
    assert response.json()["retryable"] is True


def test_an_expired_lease_is_taken_over(harness: Harness) -> None:
    run_id = _created(harness, ScriptedProvider([READY]))
    harness.update_run(
        run_id, lease_token=new_id(), lease_expires_at=utc_now() - timedelta(seconds=1)
    )

    response = harness.advance(run_id)

    assert response.status_code == 200
    assert response.json()["revision"] == 3


class CancelsMidCall:
    """Cancels the run from a second request while the model call is in flight."""

    def __init__(self, harness: Harness, run_id: Callable[[], str]) -> None:
        self.harness = harness
        self.run_id = run_id

    def generate(self, request: ModelRequest) -> ModelResult:
        response = self.harness.client.post(
            f"/api/v1/runs/{self.run_id()}/cancel",
            headers={"Idempotency-Key": "cancel-key-0001"},
        )
        assert response.status_code == 200, response.text
        return READY


def test_a_step_that_loses_the_race_is_discarded_but_its_usage_counts(harness: Harness) -> None:
    ids: list[str] = []
    run_id = _created(harness, CancelsMidCall(harness, lambda: ids[0]))
    ids.append(run_id)

    response = harness.advance(run_id)

    assert response.status_code == 409
    assert response.json()["code"] == "RUN_CHANGED"
    run = harness.client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "cancelled"
    assert run["usage"]["model_turns"] == 1
    assert harness.steps(run_id)[0].detail == {"discarded": True}


def test_a_transient_provider_error_leaves_the_run_retryable(harness: Harness) -> None:
    overloaded = ModelProviderError("unavailable", "Model provider unavailable (HTTP 503)")
    run_id = _created(harness, ScriptedProvider([overloaded, READY]))

    failed = harness.advance(run_id).json()
    assert failed["status"] == "running"
    assert failed["error"] == {
        "code": "MODEL_UNAVAILABLE",
        "message": "Model provider unavailable (HTTP 503)",
        "retryable": True,
    }
    assert failed["usage"]["model_turns"] == 1, "a failed call still counts"
    assert harness.steps(run_id)[0].error_kind == "unavailable"

    recovered = harness.advance(run_id).json()
    assert (recovered["status"], recovered["error"]) == ("running", None)


def test_a_permanent_provider_error_fails_the_run(harness: Harness) -> None:
    run_id = _created(harness, ScriptedProvider([ModelProviderError("auth", "bad key")]))

    failed = harness.advance(run_id).json()

    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "MODEL_AUTH"


def test_a_draft_still_invalid_after_its_repair_fails_the_run(harness: Harness) -> None:
    run_id = _created(harness, ScriptedProvider([READY, _result("not json"), _result("{}")]))

    harness.advance(run_id)
    failed = harness.advance(run_id).json()

    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "INVALID_MODEL_OUTPUT"


def test_a_run_without_room_for_a_draft_and_its_repair_stops_before_calling(
    harness: Harness,
) -> None:
    provider = ScriptedProvider([_ask(CANCEL_QUESTION)])
    harness.use(provider, limits=replace(LIMITS, max_turns=1))
    run_id = harness.create().json()["id"]

    failed = harness.advance(run_id).json()

    assert provider.requests == [], "the turn limit is checked before anything is sent"
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "RUN_BUDGET_EXCEEDED"


def test_a_project_cost_limit_is_enforced_before_the_call(harness: Harness) -> None:
    provider = ScriptedProvider([READY])
    harness.use(provider, project_cost_limit_microusd=1)
    run_id = harness.create().json()["id"]

    failed = harness.advance(run_id).json()

    assert provider.requests == []
    assert failed["error"]["code"] == "RUN_BUDGET_EXCEEDED"
    assert failed["project_usage"]["cost_limit_usd"] == "0.000001"


def test_injected_instructions_cannot_reach_tools_outside_the_run(harness: Harness) -> None:
    provider = ScriptedProvider(
        [
            _result(
                calls=(
                    ToolCall("c1", "approve_backlog", {"version": "all"}),
                    ToolCall("c2", "lookup_source", {"block_ids": ["B2", "B999"]}),
                )
            ),
            READY,
        ]
    )
    run_id = _created(harness, provider)

    after = harness.advance(run_id).json()
    harness.advance(run_id)

    assert after["status"] == "running"
    results = provider.requests[1].history[-1]
    assert isinstance(results, ToolResults)
    approve, lookup = results.results
    assert approve.is_error
    assert "not available" in json.dumps(approve.output)
    assert lookup.output["not_found"] == ["B999"]
    assert "Students book study rooms." in json.dumps(lookup.output)


def test_a_run_cannot_pin_another_projects_sources(harness: Harness) -> None:
    harness.use(ScriptedProvider([]))
    other = _project(harness.database_url, Role.EDITOR)
    response = harness.client.post(
        f"/api/v1/projects/{other}/runs",
        json={"mode": "initial", "source_version_ids": harness.version_ids},
        headers={"Idempotency-Key": "create-key-0002"},
    )

    assert response.status_code == 404


def test_viewers_can_read_but_not_advance_and_outsiders_see_nothing(harness: Harness) -> None:
    run_id = _created(harness, ScriptedProvider([]))
    _set_roles(harness.database_url, DEMO_PROJECT_ID, Role.VIEWER)

    assert harness.client.get(f"/api/v1/runs/{run_id}").status_code == 200
    assert harness.advance(run_id).status_code == 403

    _set_roles(harness.database_url, DEMO_PROJECT_ID)
    assert harness.client.get(f"/api/v1/runs/{run_id}").status_code == 404


def test_cancel_is_idempotent_and_final_runs_cannot_be_cancelled(harness: Harness) -> None:
    empty_patch = json.dumps({"statements": [], "items": [], "questions": []})
    run_id = _created(harness, ScriptedProvider([READY, _result(_draft()), _result(empty_patch)]))

    harness.advance(run_id)
    harness.advance(run_id)
    response = harness.client.post(
        f"/api/v1/runs/{run_id}/cancel", headers={"Idempotency-Key": harness.key()}
    )
    assert response.status_code == 409

    other = _created(harness, ScriptedProvider([]))
    for _ in range(2):
        cancelled = harness.client.post(
            f"/api/v1/runs/{other}/cancel", headers={"Idempotency-Key": harness.key()}
        )
        assert cancelled.json()["status"] == "cancelled"
    assert harness.advance(other).json()["status"] == "cancelled"


def test_creating_a_run_without_a_model_provider_is_refused(harness: Harness) -> None:
    harness.use(None)

    response = harness.create()

    assert response.status_code == 503
    assert response.json()["code"] == "MODEL_NOT_CONFIGURED"


def _project(database_url: str, *roles: Role) -> ProjectId:
    project_id = ProjectId(new_id())
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        SqlProjectRepository(session).add(
            Project(id=project_id, name="Makerspace Tool Library", created_at=utc_now())
        )
        session.commit()
    engine.dispose()
    _set_roles(database_url, project_id, *roles)
    return project_id


def _set_roles(database_url: str, project_id: UUID, *roles: Role) -> None:
    from scopesteps.identity.infrastructure.orm import MembershipRecord

    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        session.query(MembershipRecord).filter(
            MembershipRecord.user_id == LOCAL_REVIEWER_ID,
            MembershipRecord.project_id == project_id,
        ).delete()
        for role in roles:
            SqlUserRepository(session).add_membership(
                Membership(
                    user_id=LOCAL_REVIEWER_ID,
                    project_id=ProjectId(project_id),
                    role=role,
                    granted_at=utc_now(),
                )
            )
        session.commit()
    engine.dispose()


def test_a_run_only_advances_on_the_model_it_was_created_with(harness: Harness) -> None:
    run_id = _created(harness, ScriptedProvider([READY]))
    harness.use(ScriptedProvider([READY]), provider_name="groq", model_id="openai/gpt-oss-120b")

    response = harness.advance(run_id)

    assert response.status_code == 409
    assert response.json()["code"] == "RUN_MODEL_CHANGED"


BACKUP_MODEL = "openai/gpt-oss-120b"
OVERLOADED = ModelProviderError("unavailable", "Model provider unavailable (HTTP 503)")


def _with_backup(harness: Harness, primary: Any, backup: Any) -> None:
    harness.use(primary, fallback=ServedModel(backup, "groq", BACKUP_MODEL))


def test_a_run_moves_to_the_backup_when_the_primary_fails_before_any_success(
    harness: Harness,
) -> None:
    backup = ScriptedProvider([READY])
    _with_backup(harness, ScriptedProvider([OVERLOADED]), backup)
    run_id = harness.create().json()["id"]

    moved = harness.advance(run_id).json()
    assert (moved["provider"], moved["model_id"]) == ("groq", BACKUP_MODEL)
    assert moved["fallback_reason"] == "primary_model_unavailable"
    assert (moved["status"], moved["error"]) == ("running", None)
    event = harness.steps(run_id)[-1]
    assert (event.kind, event.name, event.detail["from_provider"]) == (
        "event",
        "fallback",
        "gemini",
    )

    harness.advance(run_id)
    assert len(backup.requests) == 1, "the next step runs on the backup"


def test_a_run_that_already_used_the_primary_never_switches(harness: Harness) -> None:
    primary = ScriptedProvider([_ask(CANCEL_QUESTION), OVERLOADED])
    _with_backup(harness, primary, ScriptedProvider([]))
    run_id = harness.create().json()["id"]
    waiting = harness.advance(run_id).json()
    harness.answer(run_id, waiting["questions"][0]["id"], "Two hours before.")

    failed = harness.advance(run_id).json()

    assert (failed["provider"], failed["error"]["code"]) == ("gemini", "MODEL_UNAVAILABLE")


def test_bad_output_is_repaired_not_a_reason_to_fall_back(harness: Harness) -> None:
    primary = ScriptedProvider([READY, _result("not json"), _result("{}")])
    _with_backup(harness, primary, ScriptedProvider([]))
    run_id = harness.create().json()["id"]

    harness.advance(run_id)
    failed = harness.advance(run_id).json()

    assert (failed["provider"], failed["error"]["code"]) == ("gemini", "INVALID_MODEL_OUTPUT")


def test_while_the_primary_keeps_failing_new_runs_start_on_the_backup(harness: Harness) -> None:
    _with_backup(harness, ScriptedProvider([OVERLOADED] * 3), ScriptedProvider([]))
    for _ in range(3):
        harness.advance(harness.create().json()["id"])

    fresh = harness.create().json()

    assert (fresh["provider"], fresh["fallback_reason"]) == ("groq", "primary_circuit_open")


def test_without_a_backup_the_run_stays_on_the_primary(harness: Harness) -> None:
    run_id = _created(harness, ScriptedProvider([OVERLOADED]))

    failed = harness.advance(run_id).json()

    assert (failed["provider"], failed["error"]["retryable"]) == ("gemini", True)
