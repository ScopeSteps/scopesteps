"""People named in the room-booking sources: extracted by a run, then corrected and confirmed.

The model is scripted from `fixtures/room_booking`; no test makes a live call, and every name is
synthetic.
"""

import copy
import json
import secrets
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select

from scopesteps.agent.client import RunLimits
from scopesteps.agent.domain.model import ModelResult, ModelTurn, ToolCall, Usage, UserMessage
from scopesteps.agent.http import router as agent_router
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.agent.infrastructure.repository import SqlCandidateStore
from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID, SEED_ACCOUNTS, seed
from scopesteps.backlog.client import CandidateProposal
from scopesteps.identity.client import Role
from scopesteps.identity.domain.user import Membership
from scopesteps.identity.infrastructure.orm import MembershipRecord
from scopesteps.identity.infrastructure.passwords import Argon2PasswordHasher
from scopesteps.identity.infrastructure.repository import SqlUserRepository
from scopesteps.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    utc_now,
)
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId
from scopesteps.projects.domain.project import Project
from scopesteps.projects.infrastructure.orm import PersonRecord
from scopesteps.projects.infrastructure.repository import SqlProjectRepository
from scopesteps.sources.client import quote_matches

FIXTURE = Path(__file__).parent / "fixtures" / "room_booking"
CLARIFICATION: dict[str, Any] = json.loads((FIXTURE / "clarification.json").read_text())
DRAFT: dict[str, Any] = json.loads((FIXTURE / "draft.json").read_text())
CANCEL_ANSWER = (
    "Users can cancel up to one hour before the start. Cancelling later counts as a no-show."
)
NO_CHANGES: dict[str, list[Any]] = {"statements": [], "items": [], "questions": [], "people": []}
LIMITS = RunLimits(
    max_turns=6, max_tool_calls=8, max_output_tokens_per_call=8000, max_total_tokens=200_000
)
Json = dict[str, Any]
ClientFactory = Callable[..., TestClient]
# The smallest parameters Argon2 accepts, so seeding the sign-in accounts stays fast.
WEAK_HASHER = Argon2PasswordHasher(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))


def _result(text: str = "", calls: tuple[ToolCall, ...] = ()) -> ModelResult:
    return ModelResult(
        provider="test",
        model_id="gemini-3.5-flash-lite",
        turn=ModelTurn(({"type": "model_output", "text": text},)),
        text=text or None,
        tool_calls=calls,
        finish_reason="tool_calls" if calls else "completed",
        usage=Usage(input_tokens=1000, output_tokens=100, total_tokens=1100),
        latency_ms=50,
    )


class People:
    """The room-booking project with both sources uploaded, a scripted model and the People API."""

    def __init__(self, client: TestClient, database_url: str) -> None:
        self.client = client
        self.database_url = database_url
        self.keys = 0
        self.base = f"/api/v1/projects/{DEMO_PROJECT_ID}"
        upload = client.post(
            f"{self.base}/sources",
            files={
                "brief": ("brief.md", (FIXTURE / "brief.md").read_bytes()),
                "transcript": ("transcript.md", (FIXTURE / "transcript.md").read_bytes()),
            },
            headers={"Idempotency-Key": self.key()},
        )
        assert upload.status_code == 201, upload.text
        self.source_version_ids = [version["id"] for version in upload.json()["source_versions"]]

    def key(self) -> str:
        self.keys += 1
        return f"people-key-{self.keys:04d}"

    def post(self, path: str, body: Json | None = None) -> Json:
        response = self.client.post(
            f"/api/v1{path}", json=body, headers={"Idempotency-Key": self.key()}
        )
        assert response.status_code < 300, response.text
        return response.json()

    def run(self, draft: Json = DRAFT, *, repair: Json | None = None) -> Json:
        """A whole run: the agent asks both questions, the reviewer answers one and skips the
        other, and the scripted draft arrives."""
        ask = _result(calls=(ToolCall("call-1", "request_clarification", CLARIFICATION),))
        script = [ask, _result("READY"), _result(json.dumps(draft))]
        if repair is not None:
            script.append(_result(json.dumps(repair)))
        self.client.app.state.agent_runtime = replace(  # type: ignore[attr-defined]
            self.client.app.state.agent_runtime,  # type: ignore[attr-defined]
            provider=ScriptedProvider(script),
            provider_name="gemini",
            model_id="gemini-3.5-flash-lite",
            limits=LIMITS,
        )
        run = self.post(
            f"/projects/{DEMO_PROJECT_ID}/runs",
            {"mode": "initial", "source_version_ids": self.source_version_ids},
        )
        waiting = self.post(f"/runs/{run['id']}/advance")
        for question in waiting["questions"]:
            reply = (
                {"answer": CANCEL_ANSWER}
                if question["subject"].startswith("Cancellation")
                else {"skip": True}
            )
            self.post(f"/runs/{run['id']}/answers", {"question_id": question["id"]} | reply)
        self.post(f"/runs/{run['id']}/advance")
        return self.post(f"/runs/{run['id']}/advance")

    def list(self) -> list[Json]:
        response = self.client.get(f"{self.base}/people")
        assert response.status_code == 200, response.text
        return response.json()["people"]

    def named(self, name: str) -> Json:
        return next(person for person in self.list() if person["extracted"]["name"] == name)

    def put(self, person: Json, what: str, body: Json, key: str | None = None) -> Response:
        return self.client.put(
            f"{self.base}/people/{person['id']}/{what}",
            json={"expected_revision": person["revision"]} | body,
            headers={"Idempotency-Key": key or self.key()},
        )

    def passage(self, reference: Json) -> str:
        blocks: list[Json] = self.client.get(
            f"{self.base}/sources/{reference['source_version_id']}/blocks"
        ).json()
        return next(block["text"] for block in blocks if block["id"] == reference["block_id"])

    def set_roles(self, *roles: Role) -> None:
        self._memberships(DEMO_PROJECT_ID, roles, replace_existing=True)

    def other_project(self) -> ProjectId:
        project_id = ProjectId(new_id())
        engine = create_database_engine(self.database_url)
        with create_session_factory(engine)() as session:
            SqlProjectRepository(session).add(
                Project(id=project_id, name="Makerspace Tool Library", created_at=utc_now())
            )
            session.commit()
        engine.dispose()
        self._memberships(project_id, (Role.EDITOR,), replace_existing=False)
        return project_id

    def activity(self) -> list[Json]:
        response = self.client.get(f"{self.base}/activity")
        assert response.status_code == 200, response.text
        return [e for e in response.json()["events"] if e["type"].startswith("person.")]

    def stored_people(self) -> int:
        engine = create_database_engine(self.database_url)
        with create_session_factory(engine)() as session:
            count = session.scalar(select(func.count()).select_from(PersonRecord))
        engine.dispose()
        return count or 0

    def _memberships(
        self, project_id: UUID, roles: tuple[Role, ...], *, replace_existing: bool
    ) -> None:
        engine = create_database_engine(self.database_url)
        with create_session_factory(engine)() as session:
            if replace_existing:
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


@pytest.fixture
def people(client: TestClient, seeded_database_url: str) -> People:
    return People(client, seeded_database_url)


def _edited(change: Callable[[Json], None]) -> Json:
    draft = copy.deepcopy(DRAFT)
    change(draft)
    return draft


def _person(draft: Json, name: str) -> Json:
    return next(person for person in draft["people"] if person["name"] == name)


def test_a_project_has_no_people_before_a_run(people: People) -> None:
    assert people.list() == []


def test_a_run_lists_each_person_the_sources_name_with_role_and_citations(people: People) -> None:
    run = people.run()

    listed = people.list()

    assert run["problems"] == []
    assert [(p["name"], p["role"], p["extracted"]["stated_rights"]) for p in listed] == [
        ("Dana Ruiz", "Facilities Manager, project sponsor", "decides"),
        ("Sam Okafor", "Student Union representative", "not_stated"),
        ("Priya Nair", "IT developer", "not_stated"),
        ("Alex Kim", "product owner", "not_stated"),
    ]
    for person in listed:
        extracted = person["extracted"]
        assert (person["revision"], person["project_id"]) == (1, str(DEMO_PROJECT_ID))
        assert (person["correction"], person["confirmed_rights"]) == (None, None)
        assert extracted["run_id"] == run["id"]
        assert extracted["said"]
        assert extracted["evidence"], "nobody is listed without a citation"
        assert bool(extracted["rights_evidence"]) == (extracted["stated_rights"] != "not_stated")
        for reference in (*extracted["evidence"], *extracted["rights_evidence"]):
            assert reference["source_version_id"] in people.source_version_ids
            assert quote_matches(reference["quote"], people.passage(reference))
        assert any(person["name"] in people.passage(e) for e in extracted["evidence"])


def test_a_stated_right_points_at_the_passage_that_states_it(people: People) -> None:
    people.run()

    (reference,) = people.named("Dana Ruiz")["extracted"]["rights_evidence"]

    assert reference["quote"] == "cancellation and no-shows stay open until Dana confirms"
    assert people.passage(reference).startswith("**Alex (Product owner):** Okay, cancellation")


def test_people_the_sources_do_not_name_and_uncited_rights_are_not_stored(people: People) -> None:
    def invent(draft: Json) -> None:
        draft["people"].append(
            _person(draft, "Alex Kim") | {"ref": "P5", "name": "Morgan Vale", "rights": "decides"}
        )
        _person(draft, "Sam Okafor")["rights"] = "advises"
        _person(draft, "Priya Nair")["citations"] = []

    run = people.run(_edited(invent), repair=NO_CHANGES)

    assert run["status"] == "ready_for_review"
    assert sorted(problem[:40] for problem in run["problems"]) == [
        "person P2 has rights 'advises' with no c",
        "person P3 'Priya Nair' has no citation; ",
        "person P5 'Morgan Vale' is not named in ",
        "person P5 has rights 'decides' with no c",
    ]
    assert [(p["name"], p["extracted"]["stated_rights"]) for p in people.list()] == [
        ("Dana Ruiz", "decides"),
        ("Sam Okafor", "not_stated"),
        ("Alex Kim", "not_stated"),
    ]


def test_an_editor_corrects_a_name_and_role_and_the_original_is_kept(people: People) -> None:
    people.run()
    sam = people.named("Sam Okafor")

    response = people.put(sam, "correction", {"name": "Samira Okafor", "role": "Student Union"})

    assert response.status_code == 200, response.text
    corrected = response.json()
    assert (corrected["name"], corrected["role"], corrected["revision"]) == (
        "Samira Okafor",
        "Student Union",
        2,
    )
    assert corrected["extracted"] == sam["extracted"], "the agent's reading is never overwritten"
    assert corrected["correction"]["name"] == "Samira Okafor"
    assert corrected["correction"]["role"] == "Student Union"
    assert corrected["correction"]["corrected_by"] == str(LOCAL_REVIEWER_ID)
    assert corrected["correction"]["corrected_at"] is not None
    assert people.named("Sam Okafor") == corrected


def test_correcting_only_the_role_leaves_the_name_as_extracted(people: People) -> None:
    people.run()

    corrected = people.put(people.named("Alex Kim"), "correction", {"role": "Product lead"}).json()

    assert (corrected["name"], corrected["role"]) == ("Alex Kim", "Product lead")
    assert corrected["correction"]["name"] is None


def test_a_stale_write_is_refused_and_changes_nothing(people: People) -> None:
    people.run()
    sam = people.named("Sam Okafor")
    assert people.put(sam, "correction", {"name": "Samira Okafor"}).status_code == 200

    stale_correction = people.put(sam, "correction", {"name": "S. Okafor"})
    stale_rights = people.put(sam, "rights", {"rights": "decides"})

    for response in (stale_correction, stale_rights):
        assert response.status_code == 409
        assert response.json()["code"] == "PERSON_CHANGED"
    assert stale_correction.json()["details"] == {"current_revision": 2}
    current = people.named("Sam Okafor")
    assert (current["name"], current["confirmed_rights"], current["revision"]) == (
        "Samira Okafor",
        None,
        2,
    )


def test_a_retry_with_the_same_idempotency_key_acts_once(people: People) -> None:
    people.run()
    sam = people.named("Sam Okafor")
    first = people.put(sam, "correction", {"name": "Samira Okafor"}, key="retry-key-0001")

    retried = people.put(sam, "correction", {"name": "Samira Okafor"}, key="retry-key-0001")
    reused = people.put(sam, "correction", {"name": "Someone Else"}, key="retry-key-0001")

    assert (first.status_code, retried.status_code) == (200, 200)
    assert retried.json() == first.json()
    assert (reused.status_code, reused.json()["code"]) == (409, "IDEMPOTENCY_KEY_REUSED")
    assert people.named("Sam Okafor")["revision"] == 2


def test_changes_need_an_idempotency_key_and_valid_values(people: People) -> None:
    people.run()
    sam = people.named("Sam Okafor")
    url = f"{people.base}/people/{sam['id']}"

    no_key = people.client.put(f"{url}/rights", json={"expected_revision": 1, "rights": "decides"})
    bad_right = people.put(sam, "rights", {"rights": "owns"})
    blank_name = people.put(sam, "correction", {"name": ""})
    long_role = people.put(sam, "correction", {"role": "x" * 81})
    spaces = people.put(sam, "correction", {"name": "   "})

    assert [r.status_code for r in (no_key, bad_right, blank_name, long_role, spaces)] == [422] * 5
    assert people.named("Sam Okafor") == sam


@pytest.mark.parametrize("rights", ["decides", "advises", "unknown"])
def test_an_editor_confirms_rights_the_sources_do_not_state(people: People, rights: str) -> None:
    people.run()
    sam = people.named("Sam Okafor")

    response = people.put(sam, "rights", {"rights": rights})

    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed["confirmed_rights"]["rights"] == rights
    assert confirmed["confirmed_rights"]["confirmed_by"] == str(LOCAL_REVIEWER_ID)
    assert confirmed["confirmed_rights"]["confirmed_at"] is not None
    assert confirmed["extracted"]["stated_rights"] == "not_stated", "confirming is not extracting"
    assert (confirmed["revision"], confirmed["extracted"]) == (2, sam["extracted"])


def test_rights_a_source_states_cannot_be_confirmed_by_hand(people: People) -> None:
    people.run()
    dana = people.named("Dana Ruiz")

    response = people.put(dana, "rights", {"rights": "advises"})

    assert (response.status_code, response.json()["code"]) == (409, "RIGHTS_STATED_IN_SOURCE")
    assert people.named("Dana Ruiz") == dana


def test_viewers_and_approvers_read_but_only_editors_change(people: People) -> None:
    people.run()
    sam = people.named("Sam Okafor")

    for roles in ((Role.VIEWER,), (Role.APPROVER,)):
        people.set_roles(*roles)
        assert people.list()[1] == sam
        for what, body in (("correction", {"name": "S."}), ("rights", {"rights": "decides"})):
            response = people.put(sam, what, body)
            assert (response.status_code, response.json()["code"]) == (403, "PERMISSION_DENIED")

    people.set_roles(Role.EDITOR)
    assert people.named("Sam Okafor") == sam
    assert people.put(sam, "rights", {"rights": "decides"}).status_code == 200


def test_people_are_invisible_outside_their_project(people: People) -> None:
    people.run()
    sam = people.named("Sam Okafor")
    other = people.other_project()

    elsewhere = f"/api/v1/projects/{other}/people"
    assert people.client.get(elsewhere).json() == {"people": [], "unconfirmed_speakers": []}
    for what, body in (("correction", {"name": "S."}), ("rights", {"rights": "decides"})):
        response = people.client.put(
            f"{elsewhere}/{sam['id']}/{what}",
            json={"expected_revision": 1} | body,
            headers={"Idempotency-Key": people.key()},
        )
        assert (response.status_code, response.json()["message"]) == (404, "Person not found")

    people.set_roles()
    assert people.client.get(f"{people.base}/people").status_code == 404
    hidden = people.put(sam, "correction", {"name": "S."})
    assert (hidden.status_code, hidden.json()["message"]) == (404, "Project not found")
    people.set_roles(Role.EDITOR)
    assert people.named("Sam Okafor") == sam


def test_a_later_run_keeps_corrections_and_confirmed_rights(people: People) -> None:
    first = people.run()
    sam = people.put(people.named("Sam Okafor"), "correction", {"name": "Samira Okafor"}).json()
    sam = people.put(sam, "rights", {"rights": "advises"}).json()
    priya = people.named("Priya Nair")

    def reread(draft: Json) -> None:
        _person(draft, "Sam Okafor")["said"] = "Asks whether societies can book weekly."
        draft["people"] = [p for p in draft["people"] if p["name"] != "Alex Kim"]

    second = people.run(_edited(reread))

    after = {person["extracted"]["name"]: person for person in people.list()}
    assert sorted(after) == ["Alex Kim", "Dana Ruiz", "Priya Nair", "Sam Okafor"], "no duplicates"
    again = after["Sam Okafor"]
    assert (again["id"], again["name"]) == (sam["id"], "Samira Okafor")
    assert again["correction"] == sam["correction"]
    assert again["confirmed_rights"] == sam["confirmed_rights"]
    assert again["extracted"]["said"] == "Asks whether societies can book weekly."
    assert (again["extracted"]["run_id"], again["revision"]) == (second["id"], sam["revision"] + 1)
    assert after["Priya Nair"]["revision"] == priya["revision"], "an unchanged reading"
    assert after["Priya Nair"]["extracted"]["run_id"] == second["id"]
    assert after["Alex Kim"]["extracted"]["run_id"] == first["id"], "nobody is removed"


def test_a_run_whose_backlog_is_refused_stores_no_people(
    people: People, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Refusing(SqlCandidateStore):
        def problems(self, proposal: CandidateProposal) -> list[str]:
            return ["block 0000 is not a paragraph of source version 0000"]

    monkeypatch.setattr(agent_router, "SqlCandidateStore", Refusing)

    run = people.run()

    assert (run["status"], run["error"]["code"]) == ("failed", "CANDIDATE_REFUSED")
    assert people.stored_people() == 0


def test_the_run_response_shows_the_people_the_model_wrote(people: People) -> None:
    run = people.run()

    assert [person["name"] for person in run["draft"]["people"]] == [
        "Dana Ruiz",
        "Sam Okafor",
        "Priya Nair",
        "Alex Kim",
    ]
    assert run["prompt_version"].split(",")[1].startswith("draft-v7+")


def test_an_unknown_project_or_person_is_not_found(people: People) -> None:
    people.run()
    sam = people.named("Sam Okafor")
    unknown_project = f"/api/v1/projects/{new_id()}/people"
    unknown_person = {**sam, "id": str(new_id())}

    listed = people.client.get(unknown_project)
    corrected = people.client.put(
        f"{unknown_project}/{sam['id']}/correction",
        json={"expected_revision": 1, "name": "S."},
        headers={"Idempotency-Key": people.key()},
    )
    missing = people.put(unknown_person, "rights", {"rights": "decides"})

    assert [(r.status_code, r.json()["message"]) for r in (listed, corrected, missing)] == [
        (404, "Project not found"),
        (404, "Project not found"),
        (404, "Person not found"),
    ]


def test_corrections_and_confirmations_are_in_the_activity_log_without_names(
    people: People,
) -> None:
    people.run()
    sam = people.put(people.named("Sam Okafor"), "correction", {"role": "Student Union"}).json()
    people.put(sam, "rights", {"rights": "advises"})
    people.put(sam, "correction", {"name": "S."})
    people.put(people.named("Dana Ruiz"), "rights", {"rights": "advises"})

    events = people.activity()

    assert [(e["type"], e["summary"]) for e in events] == [
        ("person.rights_confirmed", "Confirmed that a person advises on scope"),
        ("person.corrected", "Corrected a person's role"),
    ], "newest first; the stale and the refused write record nothing"
    for event in events:
        assert event["subjects"] == [{"kind": "person", "id": sam["id"]}]
        assert event["actor"]["user_id"] == str(LOCAL_REVIEWER_ID)


def test_a_signed_in_editor_changes_people_and_other_roles_cannot(
    people: People, seeded_database_url: str, make_client: ClientFactory
) -> None:
    people.run()
    sam = people.named("Sam Okafor")
    password = secrets.token_urlsafe(16)
    engine = create_database_engine(seeded_database_url)
    with create_session_factory(engine)() as session:
        seed(session, account_password=password, hasher=WEAK_HASHER)
        session.commit()
    engine.dispose()
    viewer, editor, approver = SEED_ACCOUNTS

    def signed_in(email: str) -> TestClient:
        api = make_client(seeded_database_url, auth_mode="session")
        response = api.post("/api/v1/auth/sign-in", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        return api

    def correct(api: TestClient) -> Response:
        return api.put(
            f"{people.base}/people/{sam['id']}/correction",
            json={"expected_revision": sam["revision"], "name": "Samira Okafor"},
            headers={"Idempotency-Key": people.key()},
        )

    refused = [correct(signed_in(account.email)) for account in (viewer, approver)]
    corrected = correct(signed_in(editor.email))

    assert [r.status_code for r in refused] == [403, 403]
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["correction"]["corrected_by"] == str(editor.id)
    (event,) = people.activity()
    assert event["actor"] == {
        "kind": "user",
        "user_id": str(editor.id),
        "display_name": editor.display_name,
    }


def test_people_a_run_reads_are_extracted(people: People) -> None:
    people.run()

    assert {person["origin"] for person in people.list()} == {"extracted"}
    assert all(person["meeting_role"] is None for person in people.list())


def test_a_run_fills_in_a_confirmed_speaker_and_keeps_what_the_editor_entered(
    people: People,
) -> None:
    [transcript] = people.client.get(f"{people.base}/speakers").json()["transcripts"]
    saved = people.client.put(
        f"{people.base}/sources/{transcript['source_id']}/speakers",
        json={
            "expected_revision": 0,
            "speakers": [
                {
                    "label_key": "dana",
                    "choice": "new",
                    "name": "Dana Ruiz",
                    "meeting_role": "Sponsor",
                }
            ],
        },
        headers={"Idempotency-Key": people.key()},
    )
    assert saved.status_code == 200, saved.text

    people.run()

    dana = next(person for person in people.list() if person["name"] == "Dana Ruiz")
    assert dana["origin"] == "confirmed_speaker"
    assert dana["entered_name"] == "Dana Ruiz"
    assert dana["meeting_role"]["value"] == "Sponsor"
    assert dana["extracted"]["role"] == "Facilities Manager, project sponsor"
    assert [p["name"] for p in people.list()].count("Dana Ruiz") == 1


def test_the_agent_reads_who_was_confirmed_and_keeps_the_reading_on_that_participant(
    people: People,
) -> None:
    [transcript] = people.client.get(f"{people.base}/speakers").json()["transcripts"]
    people.client.put(
        f"{people.base}/sources/{transcript['source_id']}/speakers",
        json={
            "expected_revision": 0,
            "speakers": [
                {
                    "label_key": "dana",
                    "choice": "new",
                    "name": "Dana Ruiz",
                    "meeting_role": "Sponsor",
                },
                {"label_key": "priya", "choice": "not_a_person"},
            ],
        },
        headers={"Idempotency-Key": people.key()},
    )
    dana = next(p for p in people.list() if p["name"] == "Dana Ruiz")

    people.run()

    provider = people.client.app.state.agent_runtime.provider  # type: ignore[attr-defined]
    assert isinstance(provider, ScriptedProvider)
    message = provider.requests[0].history[0]
    assert isinstance(message, UserMessage)
    first = message.text
    assert 'speakers="Dana: Dana Ruiz, Sponsor"' in first
    assert 'speakers="Sam: role unknown"' in first
    assert 'speakers="Priya: not a person"' in first
    stored = next(p for p in people.list() if p["id"] == dana["id"])
    assert stored["origin"] == "confirmed_speaker"
    assert stored["extracted"]["name"] == "Dana Ruiz"
    assert stored["meeting_role"]["value"] == "Sponsor"
