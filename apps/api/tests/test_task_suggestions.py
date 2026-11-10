"""Suggesting tasks for the stories of a draft with a scripted model: batches, saving on the draft
only, labels, scope flags, roles and failures. No test calls a real model; drafts are synthetic."""

import json
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from scopesteps.agent.domain.model import ModelProviderError, ModelResult, ModelTurn, Usage
from scopesteps.agent.infrastructure.orm import RunStepRecord
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID
from scopesteps.backlog.client import (
    CandidateProposal,
    ProposedCriterion,
    ProposedItem,
    VersionState,
    save_candidate,
)
from scopesteps.backlog.infrastructure.orm import VersionRecord
from scopesteps.identity.application.users import grant_project_role
from scopesteps.identity.client import Role
from scopesteps.identity.infrastructure.orm import MembershipRecord
from scopesteps.identity.infrastructure.repository import SqlUserRepository
from scopesteps.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    utc_now,
)
from scopesteps.kernel.ids import new_id

Json = dict[str, Any]
PROJECT = f"/api/v1/projects/{DEMO_PROJECT_ID}"
STORIES = 12
MODEL = "gemini-3.5-flash-lite"


@contextmanager
def _session(database_url: str) -> Generator[Session]:
    engine = create_database_engine(database_url)
    with create_session_factory(engine)() as session:
        yield session
        session.commit()
    engine.dispose()


def _answer(*stories: tuple[str, list[str]]) -> ModelResult:
    text = json.dumps({"stories": [{"story": s, "tasks": t} for s, t in stories]})
    return ModelResult(
        provider="test",
        model_id=MODEL,
        turn=ModelTurn(({"type": "model_output", "text": text},)),
        text=text,
        tool_calls=(),
        finish_reason="completed",
        usage=Usage(input_tokens=800, output_tokens=120, total_tokens=920),
        latency_ms=40,
    )


def _batch(first: int, count: int) -> ModelResult:
    """Two in-scope tasks for each of `count` stories, labelled from S1 as the request is."""
    return _answer(
        *(
            (f"S{n}", [f"Design the room screen {first + n}", f"Test the room flow {first + n}"])
            for n in range(1, count + 1)
        )
    )


class Draft:
    """The demo project with a draft of one epic and twelve small stories."""

    def __init__(self, client: TestClient, database_url: str) -> None:
        self.client = client
        self.database_url = database_url
        self.keys = 0
        uploaded = client.post(
            f"{PROJECT}/sources",
            files={"brief": ("brief.md", b"# Rooms\n\nStudents book study rooms.")},
            headers={"Idempotency-Key": "task-upload-0001"},
        )
        assert uploaded.status_code == 201, uploaded.text
        brief = UUID(uploaded.json()["source_versions"][0]["id"])
        proposal = CandidateProposal(
            project_id=DEMO_PROJECT_ID,
            run_id=new_id(),
            created_by=LOCAL_REVIEWER_ID,
            source_version_ids=(brief,),
            items=(
                ProposedItem("E1", "epic", None, "Room booking", "Booking study rooms."),
                *(
                    ProposedItem(
                        f"S{n}",
                        "story",
                        "E1",
                        f"Book room {n}",
                        f"As a student, I want to book room {n}, so that I can study there.",
                        criteria=(ProposedCriterion(f"A student books room {n}.", proposed=False),),
                    )
                    for n in range(1, STORIES + 1)
                ),
            ),
            decisions=(),
        )
        with _session(database_url) as session:
            self.id = save_candidate(session, proposal, utc_now())

    def script(self, *answers: ModelResult | ModelProviderError) -> ScriptedProvider:
        provider = ScriptedProvider(list(answers))
        self.client.app.state.agent_runtime = replace(  # type: ignore[attr-defined]
            self.client.app.state.agent_runtime,  # type: ignore[attr-defined]
            provider=provider,
            provider_name="gemini",
            model_id=MODEL,
        )
        return provider

    def key(self) -> str:
        self.keys += 1
        return f"task-run-key-{self.keys:04d}"

    def get(self) -> Json:
        response = self.client.get(f"{PROJECT}/backlogs/{self.id}")
        assert response.status_code == 200, response.text
        return response.json()

    def stories(self) -> list[Json]:
        return [item for item in self.get()["items"] if item["kind"] == "story"]

    def start(self, story_ids: list[str] | None = None, key: str | None = None) -> Response:
        body = {} if story_ids is None else {"story_ids": story_ids}
        return self.client.post(
            f"{PROJECT}/backlogs/{self.id}/task-suggestions",
            json=body,
            headers={"Idempotency-Key": key or self.key()},
        )

    def advance(self, run: Json) -> Json:
        response = self.client.post(
            f"/api/v1/runs/{run['id']}/advance", headers={"Idempotency-Key": self.key()}
        )
        assert response.status_code == 200, response.text
        return response.json()

    def checks(self, run: Json) -> list[Json]:
        with _session(self.database_url) as session:
            return [
                step.detail
                for step in session.scalars(
                    select(RunStepRecord)
                    .where(RunStepRecord.run_id == UUID(run["id"]))
                    .order_by(RunStepRecord.sequence)
                )
                if step.name == "validate_tasks"
            ]

    def hold_role(self, role: Role | None) -> None:
        with _session(self.database_url) as session:
            session.execute(
                delete(MembershipRecord).where(
                    MembershipRecord.user_id == LOCAL_REVIEWER_ID,
                    MembershipRecord.project_id == DEMO_PROJECT_ID,
                )
            )
            if role is not None:
                grant_project_role(
                    SqlUserRepository(session), LOCAL_REVIEWER_ID, DEMO_PROJECT_ID, role, utc_now()
                )


@pytest.fixture
def draft(
    client: TestClient, seeded_database_url: str, confirm_speakers: Callable[[TestClient], None]
) -> Draft:
    made = Draft(client, seeded_database_url)
    confirm_speakers(client)
    return made


def test_suggestions_for_every_story_arrive_in_batches_labelled_suggested(draft: Draft) -> None:
    provider = draft.script(_batch(0, 10), _batch(10, 2))

    run = draft.start().json()
    first = draft.advance(run)
    after_first = draft.stories()
    last = draft.advance(first)

    assert (run["mode"], run["stage"], run["status"], run["prompt_version"]) == (
        "tasks",
        "tasks",
        "created",
        "tasks-v2",
    )
    assert first["status"] == "running"
    assert sum(1 for story in after_first if story["tasks"]) == 10
    assert last["status"] == "completed"
    stories = draft.stories()
    assert all(len(story["tasks"]) == 2 for story in stories)
    assert {(t["origin"], t["suggestion"]) for s in stories for t in s["tasks"]} == {
        ("suggested", "pending")
    }
    assert stories[11]["tasks"][0]["title"] == "Design the room screen 12"
    assert [check["stories"] for check in draft.checks(run)] == [10, 2]
    assert len(provider.requests) == 2
    assert '<story id="S1">' in str(provider.requests[0].history[0])


def test_a_story_run_touches_only_the_chosen_stories_and_replaces_its_unreviewed_ones(
    draft: Draft,
) -> None:
    story = draft.stories()[3]
    draft.script(_answer(("S1", ["Design the room screen"])), _answer(("S1", ["Test the flow"])))

    first = draft.start([story["id"]]).json()
    draft.advance(first)
    again = draft.start([story["id"]]).json()
    draft.advance(again)

    stories = draft.stories()
    assert [t["title"] for t in stories[3]["tasks"]] == ["Test the flow"]
    assert all(not s["tasks"] for i, s in enumerate(stories) if i != 3)


def test_a_task_outside_its_story_is_saved_flagged_and_counted(draft: Draft) -> None:
    story = draft.stories()[0]
    draft.script(_answer(("S1", ["Design the room screen", "Set up the payment provider"])))

    run = draft.start([story["id"]]).json()
    draft.advance(run)

    tasks = draft.stories()[0]["tasks"]
    assert [t["flag"] is None for t in tasks] == [True, False]
    assert tasks[1]["flag"]["code"] == "new_work"
    assert draft.checks(run)[0]["flagged"] == 1


def test_a_provider_failure_is_tried_again_and_saves_nothing_until_it_works(draft: Draft) -> None:
    story = draft.stories()[0]
    draft.script(
        ModelProviderError("unavailable", "The model is busy", status_code=503),
        _answer(("S1", ["Design the room screen"])),
    )

    run = draft.start([story["id"]]).json()
    failed = draft.advance(run)
    unchanged = draft.stories()[0]["tasks"]
    done = draft.advance(failed)

    assert (failed["status"], failed["error"]["retryable"]) == ("running", True)
    assert unchanged == []
    assert done["status"] == "completed"
    assert [t["title"] for t in draft.stories()[0]["tasks"]] == ["Design the room screen"]


def test_an_answer_that_is_not_valid_fails_the_run_and_saves_nothing(draft: Draft) -> None:
    draft.script(
        ModelResult(
            provider="test",
            model_id=MODEL,
            turn=ModelTurn(({"type": "model_output", "text": "not json"},)),
            text="not json",
            tool_calls=(),
            finish_reason="completed",
            usage=Usage(),
            latency_ms=1,
        )
    )

    run = draft.advance(draft.start().json())

    assert (run["status"], run["error"]["code"]) == ("failed", "INVALID_OUTPUT")
    assert all(not story["tasks"] for story in draft.stories())


def test_a_draft_approved_mid_run_gets_no_suggestions_and_the_run_fails(draft: Draft) -> None:
    draft.script(_batch(0, 10))
    run = draft.start().json()
    with _session(draft.database_url) as session:
        session.get_one(VersionRecord, draft.id).state = VersionState.APPROVED

    failed = draft.advance(run)

    assert (failed["status"], failed["error"]["code"]) == ("failed", "VERSION_NOT_DRAFT")
    assert all(not story["tasks"] for story in draft.stories())


def test_tasks_are_never_suggested_on_a_version_that_is_not_a_draft(draft: Draft) -> None:
    with _session(draft.database_url) as session:
        session.get_one(VersionRecord, draft.id).state = VersionState.APPROVED
    draft.script()

    response = draft.start()

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "VERSION_NOT_DRAFT"


@pytest.mark.parametrize("story_ids", [[str(UUID(int=5))], []], ids=["unknown story", "empty list"])
def test_stories_must_belong_to_the_draft(draft: Draft, story_ids: list[str]) -> None:
    draft.script()

    response = draft.start(story_ids)

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    ("role", "status"),
    [(None, 404), (Role.VIEWER, 403), (Role.EDITOR, 201), (Role.APPROVER, 201)],
)
def test_editors_and_approvers_ask_for_tasks_and_viewers_cannot(
    draft: Draft, role: Role | None, status: int
) -> None:
    draft.script()
    draft.hold_role(role)

    response = draft.start()

    assert response.status_code == status, response.text


def test_asking_twice_with_one_key_starts_one_run(draft: Draft) -> None:
    draft.script()

    first = draft.start(key="same-task-key-1")
    again = draft.start(key="same-task-key-1")

    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json()["id"] == first.json()["id"]


def test_a_story_whose_only_task_says_it_again_gets_no_task(draft: Draft) -> None:
    first, second = draft.stories()[:2]
    draft.script(
        _answer(
            ("S1", ["Build booking for room 1"]),
            ("S2", ["Design the room screen", "Build booking for room 2"]),
        )
    )

    run = draft.start([first["id"], second["id"]]).json()
    draft.advance(run)

    stories = draft.stories()
    assert stories[0]["tasks"] == []
    assert [t["title"] for t in stories[1]["tasks"]] == [
        "Design the room screen",
        "Build booking for room 2",
    ]
    assert draft.checks(run)[0]["restated"] == 1
