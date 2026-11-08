"""An agent run drafts with draft-v11 in steps: the outline in one advance, then each epic's stories
in its own (ADR 0028). The room-booking draft the one-call tests use is split into those steps,
so both paths are held to the same backlog. Scripted model only.
"""

import copy
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from scopesteps.agent.client import RunLimits
from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelResult,
    ModelTurn,
    ToolCall,
    Usage,
)
from scopesteps.agent.infrastructure.orm import RunStepRecord
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.api.seed import DEMO_PROJECT_ID
from scopesteps.infrastructure.database import create_database_engine, create_session_factory

FIXTURE = Path(__file__).parent / "fixtures" / "room_booking"
CLARIFICATION: dict[str, Any] = json.loads((FIXTURE / "clarification.json").read_text())
DRAFT: dict[str, Any] = json.loads((FIXTURE / "draft.json").read_text())
CANCELLATION = "Cancellation and no-shows"
CANCEL_ANSWER = (
    "Users can cancel up to one hour before the start. Cancelling later counts as a no-show."
)
MODEL = "gemini-3.5-flash-lite"
LIMITS = RunLimits(
    max_turns=20, max_tool_calls=8, max_output_tokens_per_call=8000, max_total_tokens=600_000
)
Json = dict[str, Any]


def _outline(draft: Json = DRAFT) -> Json:
    """The draft's statements, questions and people, with each epic covering its stories'
    statements."""
    epics: list[Json] = []
    for epic in (item for item in draft["items"] if item["kind"] == "epic"):
        stories = [i for i in draft["items"] if i["parent_ref"] == epic["ref"]]
        epics.append(
            {
                "ref": epic["ref"],
                "title": epic["title"],
                "description": epic["description"],
                "criteria": epic["criteria"],
                "covers": [ref for story in stories for ref in story["covers"]],
            }
        )
    questions = [{k: v for k, v in q.items() if k != "affects"} for q in draft["questions"]]
    return {
        "statements": draft["statements"],
        "epics": epics,
        "questions": questions,
        "people": draft["people"],
    }


def _stories(epic_ref: str, draft: Json = DRAFT) -> Json:
    """An epic's stories as its own step writes them: numbered within the epic, and waiting for
    the questions that affect them."""
    stories = [i for i in draft["items"] if i["parent_ref"] == epic_ref]
    written: list[Json] = []
    for number, story in enumerate(stories, start=1):
        waits = [
            index
            for index, question in enumerate(draft["questions"], start=1)
            if story["ref"] in question["affects"]
        ]
        fields = {k: v for k, v in story.items() if k not in {"kind", "parent_ref"}}
        written.append(fields | {"ref": f"S{number}", "waits_for": waits})
    return {"stories": written}


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


def _json(payload: Json) -> ModelResult:
    return _result(json.dumps(payload))


class Rooms:
    """The room-booking project with a scripted model, run until the draft starts."""

    def __init__(self, client: TestClient, database_url: str) -> None:
        self.client = client
        self.database_url = database_url
        self.keys = 0
        response = client.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/sources",
            files={
                "brief": ("brief.md", (FIXTURE / "brief.md").read_bytes()),
                "transcript": ("transcript.md", (FIXTURE / "transcript.md").read_bytes()),
            },
            headers={"Idempotency-Key": self.key()},
        )
        assert response.status_code == 201, response.text
        self.versions = [version["id"] for version in response.json()["source_versions"]]

    def key(self) -> str:
        self.keys += 1
        return f"stepwise-key-{self.keys:04d}"

    def post(self, path: str, body: Json | None = None) -> Json:
        response = self.client.post(
            f"/api/v1{path}", json=body, headers={"Idempotency-Key": self.key()}
        )
        assert response.status_code < 300, response.text
        return response.json()

    def start(
        self, drafting: list[ModelResult | ModelProviderError], limits: RunLimits = LIMITS
    ) -> Json:
        """Create a run, answer its questions, and stop where the draft begins."""
        ask = _result(calls=(ToolCall("call-1", "request_clarification", CLARIFICATION),))
        self.client.app.state.agent_runtime = replace(  # type: ignore[attr-defined]
            self.client.app.state.agent_runtime,  # type: ignore[attr-defined]
            provider=ScriptedProvider([ask, _result("READY"), *drafting]),
            provider_name="gemini",
            model_id=MODEL,
            limits=limits,
        )
        run = self.post(
            f"/projects/{DEMO_PROJECT_ID}/runs",
            {"mode": "initial", "source_version_ids": self.versions},
        )
        waiting = self.post(f"/runs/{run['id']}/advance")
        for question in waiting["questions"]:
            reply = CANCEL_ANSWER if question["subject"] == CANCELLATION else None
            body = {"question_id": question["id"]} | (
                {"answer": reply} if reply else {"skip": True}
            )
            self.post(f"/runs/{run['id']}/answers", body)
        return self.post(f"/runs/{run['id']}/advance")

    def advance(self, run: Json) -> Json:
        return self.post(f"/runs/{run['id']}/advance")

    def checks(self, run: Json) -> list[dict[str, Any]]:
        """The details of the run's validate_backlog steps, in order."""
        engine = create_database_engine(self.database_url)
        with create_session_factory(engine)() as session:
            details = [
                step.detail
                for step in session.scalars(
                    select(RunStepRecord)
                    .where(RunStepRecord.run_id == UUID(run["id"]))
                    .order_by(RunStepRecord.sequence)
                )
                if step.name == "validate_backlog"
            ]
        engine.dispose()
        return details


@pytest.fixture
def rooms(
    client: TestClient, seeded_database_url: str, confirm_speakers: Callable[[TestClient], None]
) -> Rooms:
    rooms_ = Rooms(client, seeded_database_url)
    confirm_speakers(client)
    return rooms_


def test_a_run_writes_the_outline_then_each_epic_in_its_own_advance(rooms: Rooms) -> None:
    explored = rooms.start([_json(_outline()), _json(_stories("E1")), _json(_stories("E2"))])
    assert explored["prompt_version"].startswith("explore-v3+"), "new runs pin draft-v11"
    assert explored["prompt_version"].split(",")[1].startswith("draft-v15+")

    outlined = rooms.advance(explored)
    first = rooms.advance(outlined)
    ready = rooms.advance(first)

    assert [r["status"] for r in (outlined, first)] == ["running", "running"]
    assert "draft_progress" not in outlined, "finished steps are model output and stay private"
    assert outlined["draft"] is None
    assert outlined["drafting"] == {"outline_written": True, "epics": 2, "epics_written": 0}
    assert first["drafting"]["epics_written"] == 1
    assert ready["drafting"] is None
    assert ready["coverage"] == {"confirmed": 6, "covered": 6, "uncovered": []}
    assert ready["status"] == "ready_for_review", ready
    assert ready["problems"] == []
    assert [(i["ref"], i["parent_ref"]) for i in ready["draft"]["items"]] == [
        (i["ref"], i["parent_ref"]) for i in DRAFT["items"]
    ], "the same backlog as the one-call draft"
    assert ready["draft"]["questions"][0]["affects"] == ["S2"]
    assert ready["usage"]["model_turns"] == 5, "ask, ready, outline, two epics"
    checked = [detail["draft_step"] for detail in rooms.checks(ready)]
    assert checked == ["outline", "epic 1 of 2", "epic 2 of 2", "backlog"]


def test_a_run_whose_epics_cannot_all_fit_fails_before_writing_any(rooms: Rooms) -> None:
    tight = replace(LIMITS, max_turns=6)
    explored = rooms.start([_json(_outline())], limits=tight)

    failed = rooms.advance(explored)

    assert failed["status"] == "failed"
    assert failed["error"]["message"].startswith("The sources need 2 epics, and this run cannot")
    assert failed["usage"]["model_turns"] == 3, "no epic was written"


def test_an_epic_that_fails_at_the_provider_is_tried_again_on_its_own(rooms: Rooms) -> None:
    busy = ModelProviderError("unavailable", "overloaded")
    explored = rooms.start([_json(_outline()), _json(_stories("E1")), busy, _json(_stories("E2"))])

    first = rooms.advance(rooms.advance(explored))
    retried = rooms.advance(first)
    ready = rooms.advance(retried)

    assert (retried["status"], retried["error"]["retryable"]) == ("running", True)
    assert ready["status"] == "ready_for_review", ready
    assert ready["usage"]["model_turns"] == 6, "the failed call counts; nothing was redone"


def test_an_epic_that_never_validates_fails_the_run_and_names_it(rooms: Rooms) -> None:
    empty: Json = {"stories": []}
    explored = rooms.start([_json(_outline()), _json(_stories("E1")), _json(empty), _json(empty)])

    failed = rooms.advance(rooms.advance(rooms.advance(explored)))

    assert failed["status"] == "failed"
    assert failed["error"]["message"] == (
        f'The model did not return valid stories for epic 2 of 2 ("{DRAFT["items"][4]["title"]}") '
        "after its repair attempt"
    )


def test_a_backlog_past_the_old_ceiling_of_2_epics_and_8_stories_is_saved(rooms: Rooms) -> None:
    bigger = copy.deepcopy(DRAFT)
    extra_epic = copy.deepcopy(bigger["items"][4]) | {"ref": "E3", "title": "Reporting"}
    extras = [
        copy.deepcopy(bigger["items"][5])
        | {"ref": f"S{n}", "parent_ref": "E3", "title": f"Report {n}"}
        for n in range(6, 12)
    ]
    bigger["items"] += [extra_epic, *extras]
    explored = rooms.start(
        [
            _json(_outline(bigger)),
            _json(_stories("E1", bigger)),
            _json(_stories("E2", bigger)),
            _json(_stories("E3", bigger)),
        ]
    )

    ready = rooms.advance(rooms.advance(rooms.advance(rooms.advance(explored))))

    assert ready["status"] == "ready_for_review", ready
    backlog = rooms.client.get(
        f"/api/v1/projects/{DEMO_PROJECT_ID}/backlogs/{ready['candidate_version_id']}"
    ).json()
    kinds = [item["kind"] for item in backlog["items"]]
    assert (kinds.count("epic"), kinds.count("story")) == (3, 11)


def test_a_requirement_no_story_covers_is_listed_with_its_quotes(rooms: Rooms) -> None:
    without_t9 = _stories("E1")
    without_t9["stories"] = [
        story for story in without_t9["stories"] if "T9" not in story["covers"]
    ]
    explored = rooms.start(
        [_json(_outline()), _json(without_t9), _json(without_t9), _json(_stories("E2"))]
    )

    ready = rooms.advance(rooms.advance(rooms.advance(explored)))

    assert ready["status"] == "ready_for_review", ready
    t9 = next(s for s in DRAFT["statements"] if s["id"] == "T9")
    assert ready["coverage"] == {
        "confirmed": 6,
        "covered": 5,
        "uncovered": [
            {"statement_id": "T9", "summary": t9["summary"], "citations": t9["citations"]}
        ],
    }
    assert any("T9" in problem for problem in ready["problems"])
