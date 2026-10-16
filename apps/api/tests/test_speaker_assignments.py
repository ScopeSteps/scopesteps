"""Who's who in uploaded transcripts through the API. Every name here is fictional."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import delete
from sqlalchemy.orm import Session

from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID
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
from scopesteps.projects.domain.project import Project
from scopesteps.projects.infrastructure.repository import SqlProjectRepository

ClientFactory = Callable[..., TestClient]
Json = dict[str, Any]

BASE = f"/api/v1/projects/{DEMO_PROJECT_ID}"
KICKOFF = (
    b"Mira Holt   0:03\nThe main problem is people arriving when every stand is taken.\n\n"
    b"Tomas Reed   0:15\nHalf the calls I get are about space.\n\n"
    b"Speaker 3   0:21\nCan we pay for parts?"
)
FOLLOW_UP = b"Mira Holt: We kept one slot per person.\n\nSpeaker 3: Still asking about parts."


def _session(database_url: str) -> Session:
    return create_session_factory(create_database_engine(database_url))()


def _set_roles(database_url: str, project_id: ProjectId, *roles: Role) -> None:
    with _session(database_url) as session:
        session.execute(
            delete(MembershipRecord).where(
                MembershipRecord.user_id == LOCAL_REVIEWER_ID,
                MembershipRecord.project_id == project_id,
            )
        )
        for role in roles:
            SqlUserRepository(session).add_membership(
                Membership(
                    user_id=LOCAL_REVIEWER_ID,
                    project_id=project_id,
                    role=role,
                    granted_at=utc_now(),
                )
            )
        session.commit()


class WhosWho:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.keys = 0

    def key(self) -> str:
        self.keys += 1
        return f"whos-who-{self.keys:04d}"

    def upload(self, content: bytes, filename: str = "kickoff.txt") -> Json:
        response = self.client.post(
            f"{BASE}/sources",
            files={"transcript": (filename, content)},
            headers={"Idempotency-Key": self.key()},
        )
        assert response.status_code == 201, response.text
        return response.json()["source_versions"][0]

    def transcripts(self) -> list[Json]:
        response = self.client.get(f"{BASE}/speakers")
        assert response.status_code == 200, response.text
        return response.json()["transcripts"]

    def transcript(self, source_id: str) -> Json:
        return next(t for t in self.transcripts() if t["source_id"] == source_id)

    def put(
        self, source_id: str, speakers: list[Json], revision: int = 0, key: str | None = None
    ) -> Response:
        return self.client.put(
            f"{BASE}/sources/{source_id}/speakers",
            json={"expected_revision": revision, "speakers": speakers},
            headers={"Idempotency-Key": key or self.key()},
        )

    def people(self) -> Json:
        response = self.client.get(f"{BASE}/people")
        assert response.status_code == 200, response.text
        return response.json()

    def activity(self) -> list[Json]:
        events = self.client.get(f"{BASE}/activity").json()["events"]
        return [event for event in events if event["type"] == "speakers.confirmed"]


@pytest.fixture
def whos_who(client: TestClient) -> WhosWho:
    return WhosWho(client)


def _statuses(transcript: Json) -> dict[str, str]:
    return {speaker["key"]: speaker["status"] for speaker in transcript["speakers"]}


def test_lists_every_transcript_s_speakers_as_unconfirmed_at_first(whos_who: WhosWho) -> None:
    kickoff = whos_who.upload(KICKOFF)

    [transcript] = whos_who.transcripts()

    assert transcript["source_id"] == kickoff["source_id"]
    assert transcript["source_version_id"] == kickoff["id"]
    assert transcript["revision"] == 0
    assert [(s["label"], s["status"], s["person_id"]) for s in transcript["speakers"]] == [
        ("Mira Holt", "unconfirmed", None),
        ("Tomas Reed", "unconfirmed", None),
        ("Speaker 3", "unconfirmed", None),
    ]
    people = whos_who.people()
    assert [s["label"] for s in people["unconfirmed_speakers"]] == [
        "Mira Holt",
        "Tomas Reed",
        "Speaker 3",
    ]


def test_creates_links_and_marks_not_a_person_in_one_save(whos_who: WhosWho) -> None:
    kickoff = whos_who.upload(KICKOFF)

    response = whos_who.put(
        kickoff["source_id"],
        [
            {
                "label_key": "mira holt",
                "choice": "new",
                "name": "Mira Holt",
                "meeting_role": "Sponsor",
            },
            {"label_key": "tomas reed", "choice": "new", "name": "Tomas Reed"},
            {"label_key": "speaker 3", "choice": "not_a_person"},
        ],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 1
    assert _statuses(body) == {
        "mira holt": "linked",
        "tomas reed": "linked",
        "speaker 3": "not_a_person",
    }
    assert all(s["assigned_by"] == str(LOCAL_REVIEWER_ID) for s in body["speakers"])
    people = whos_who.people()
    assert people["unconfirmed_speakers"] == []
    mira = next(p for p in people["people"] if p["name"] == "Mira Holt")
    assert mira["origin"] == "confirmed_speaker"
    assert mira["entered_name"] == "Mira Holt"
    assert mira["extracted"] is None
    assert mira["meeting_role"]["value"] == "Sponsor"
    assert mira["spoke_in"] == [
        {"source_id": kickoff["source_id"], "label": "Mira Holt", "status": "linked"}
    ]


def test_links_two_labels_to_one_participant(whos_who: WhosWho) -> None:
    kickoff = whos_who.upload(KICKOFF)
    first = whos_who.put(
        kickoff["source_id"], [{"label_key": "mira holt", "choice": "new", "name": "Mira Holt"}]
    ).json()
    mira_id = first["speakers"][0]["person_id"]

    second = whos_who.put(
        kickoff["source_id"],
        [
            {"label_key": "mira holt", "choice": "link", "person_id": mira_id},
            {"label_key": "speaker 3", "choice": "link", "person_id": mira_id},
        ],
        revision=1,
    ).json()

    assert [s["person_id"] for s in second["speakers"] if s["status"] == "linked"] == [
        mira_id,
        mira_id,
    ]


def test_records_the_save_in_activity_without_names(whos_who: WhosWho) -> None:
    kickoff = whos_who.upload(KICKOFF)

    whos_who.put(
        kickoff["source_id"],
        [
            {"label_key": "mira holt", "choice": "new", "name": "Mira Holt"},
            {"label_key": "speaker 3", "choice": "not_a_person"},
        ],
    )

    [event] = whos_who.activity()
    assert event["summary"] == (
        "Confirmed who's who in a transcript: 1 speaker linked, 1 new participant, 1 not a person"
    )
    assert "Mira" not in str(event)


def test_a_stale_revision_is_a_conflict_with_the_current_one(whos_who: WhosWho) -> None:
    kickoff = whos_who.upload(KICKOFF)
    whos_who.put(kickoff["source_id"], [{"label_key": "speaker 3", "choice": "not_a_person"}])

    response = whos_who.put(
        kickoff["source_id"], [{"label_key": "tomas reed", "choice": "not_a_person"}], revision=0
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SPEAKERS_CHANGED"
    assert response.json()["details"]["current_revision"] == 1


@pytest.mark.parametrize(
    "answer",
    [
        {"label_key": "mira holt", "choice": "new", "name": "   "},
        {"label_key": "mira holt", "choice": "new", "name": "Mira", "meeting_role": "R" * 81},
        {"label_key": "mira holt", "choice": "new", "name": "M" * 81},
        {"label_key": "nobody", "choice": "not_a_person"},
        {"label_key": "mira holt", "choice": "guess"},
    ],
)
def test_invalid_answers_are_unprocessable(whos_who: WhosWho, answer: Json) -> None:
    kickoff = whos_who.upload(KICKOFF)

    response = whos_who.put(kickoff["source_id"], [answer])

    assert response.status_code == 422
    assert whos_who.transcript(kickoff["source_id"])["revision"] == 0


def test_a_retry_with_the_same_key_returns_the_same_result(whos_who: WhosWho) -> None:
    kickoff = whos_who.upload(KICKOFF)
    answer = [{"label_key": "mira holt", "choice": "new", "name": "Mira Holt"}]

    first = whos_who.put(kickoff["source_id"], answer, key="retry-0001")
    again = whos_who.put(kickoff["source_id"], answer, key="retry-0001")

    assert again.status_code == 200
    assert again.json() == first.json()
    assert len(whos_who.people()["people"]) == 1
    assert len(whos_who.activity()) == 1


def test_a_new_participant_with_a_known_name_is_refused(whos_who: WhosWho) -> None:
    kickoff = whos_who.upload(KICKOFF)
    whos_who.put(
        kickoff["source_id"], [{"label_key": "mira holt", "choice": "new", "name": "Mira Holt"}]
    )

    response = whos_who.put(
        kickoff["source_id"],
        [{"label_key": "speaker 3", "choice": "new", "name": "mira holt"}],
        revision=1,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "PARTICIPANT_EXISTS"
    assert response.json()["details"]["field"] == "speakers[0].name"


def test_a_new_version_keeps_the_answers_and_a_later_transcript_links_itself(
    whos_who: WhosWho,
) -> None:
    kickoff = whos_who.upload(KICKOFF)
    whos_who.put(
        kickoff["source_id"],
        [
            {"label_key": "mira holt", "choice": "new", "name": "Mira Holt"},
            {"label_key": "speaker 3", "choice": "new", "name": "Tomas Reed"},
        ],
    )
    revised = whos_who.client.post(
        f"{BASE}/sources/{kickoff['source_id']}/versions",
        files={"file": ("kickoff.txt", KICKOFF + b"\n\nMira Holt   0:40\nThanks, all.")},
        headers={"Idempotency-Key": whos_who.key()},
    ).json()
    follow_up = whos_who.upload(FOLLOW_UP, "follow-up.txt")

    first, second = whos_who.transcripts()

    assert first["source_version_id"] == revised["id"]
    assert _statuses(first)["mira holt"] == "linked"
    assert _statuses(second) == {"mira holt": "linked_automatically", "speaker 3": "unconfirmed"}
    assert second["source_id"] == follow_up["source_id"]


def test_saving_needs_the_editor_role_and_reading_any_role(
    whos_who: WhosWho, seeded_database_url: str
) -> None:
    kickoff = whos_who.upload(KICKOFF)
    _set_roles(seeded_database_url, DEMO_PROJECT_ID, Role.VIEWER, Role.APPROVER)

    response = whos_who.put(
        kickoff["source_id"], [{"label_key": "speaker 3", "choice": "not_a_person"}]
    )

    assert response.status_code == 403
    assert whos_who.client.get(f"{BASE}/speakers").status_code == 200
    assert whos_who.client.get(f"{BASE}/people").status_code == 200


def test_another_project_s_source_and_a_brief_are_not_found(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    client = make_client(seeded_database_url)
    whos_who = WhosWho(client)
    kickoff = whos_who.upload(KICKOFF)
    brief = client.post(
        f"{BASE}/sources",
        files={"brief": ("brief.md", b"Mira Holt: a brief that looks like a turn.")},
        headers={"Idempotency-Key": whos_who.key()},
    ).json()["source_versions"][0]
    other = ProjectId(new_id())
    with _session(seeded_database_url) as session:
        SqlProjectRepository(session).add(
            Project(id=other, name="Makerspace Tool Library", created_at=utc_now())
        )
        session.commit()
    _set_roles(seeded_database_url, other, Role.EDITOR)
    answer: Json = {"expected_revision": 0, "speakers": []}

    through_other = client.put(
        f"/api/v1/projects/{other}/sources/{kickoff['source_id']}/speakers",
        json=answer,
        headers={"Idempotency-Key": "other-0001"},
    )
    of_brief = whos_who.put(brief["source_id"], [])

    for response in (through_other, of_brief):
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"
        assert "Mira" not in response.text
