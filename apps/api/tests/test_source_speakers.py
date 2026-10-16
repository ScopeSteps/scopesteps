"""Speaker labels the API finds in uploaded transcripts. Every name here is fictional."""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import delete, func, select, update
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
from scopesteps.sources.infrastructure.orm import SourceVersionRecord, SpeakerLabelRecord

ClientFactory = Callable[..., TestClient]

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCES_URL = f"/api/v1/projects/{DEMO_PROJECT_ID}/sources"
TRANSCRIPT = (
    b"Kickoff meeting: Bike Repair Workshop\n\n"
    b"Mira Holt   0:03\nThe main problem is people arriving when every stand is taken.\n\n"
    b"Tomas Reed   0:15\nHalf the calls I get are about space.\n\n"
    b"Mira Holt   0:21\nOne slot per person per Saturday."
)


def _upload(client: TestClient, kind: str, content: bytes, key: str) -> dict[str, str]:
    response = client.post(
        SOURCES_URL,
        files={kind: (f"{kind}.txt", content)},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text
    return response.json()["source_versions"][0]


def _speakers(client: TestClient, source_id: str, project: ProjectId = DEMO_PROJECT_ID) -> Response:
    return client.get(f"/api/v1/projects/{project}/sources/{source_id}/speakers")


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


def _other_project(database_url: str) -> ProjectId:
    project_id = ProjectId(new_id())
    with _session(database_url) as session:
        SqlProjectRepository(session).add(
            Project(id=project_id, name="Makerspace Tool Library", created_at=utc_now())
        )
        session.commit()
    _set_roles(database_url, project_id, Role.EDITOR)
    return project_id


def test_lists_each_speaker_in_an_uploaded_transcript(client: TestClient) -> None:
    transcript = _upload(client, "transcript", TRANSCRIPT, "upload-0001")
    blocks = client.get(f"{SOURCES_URL}/{transcript['id']}/blocks").json()

    response = _speakers(client, transcript["source_id"])

    assert response.status_code == 200
    assert response.json() == {
        "source_id": transcript["source_id"],
        "source_version_id": transcript["id"],
        "source_kind": "transcript",
        "speakers": [
            {
                "key": "mira holt",
                "label": "Mira Holt",
                "turn_count": 2,
                "first_block_id": blocks[1]["id"],
                "first_paragraph": 2,
                "sample": "The main problem is people arriving when every stand is taken.",
            },
            {
                "key": "tomas reed",
                "label": "Tomas Reed",
                "turn_count": 1,
                "first_block_id": blocks[2]["id"],
                "first_paragraph": 3,
                "sample": "Half the calls I get are about space.",
            },
        ],
    }


def test_the_sample_transcript_s_pasted_note_is_not_a_speaker(client: TestClient) -> None:
    content = (REPO_ROOT / "samples/sources/valid/transcript.txt").read_bytes()
    transcript = _upload(client, "transcript", content, "upload-0001")

    speakers = _speakers(client, transcript["source_id"]).json()["speakers"]

    assert [(s["label"], s["turn_count"]) for s in speakers] == [
        ("Mira", 5),
        ("Tomas", 3),
        ("Ana", 3),
    ]


def test_labels_and_samples_come_back_as_the_plain_text_written(client: TestClient) -> None:
    content = b"<v Mira Holt><b>Hello</b> &amp; welcome.</v>"
    transcript = _upload(client, "transcript", content, "upload-0001")

    [speaker] = _speakers(client, transcript["source_id"]).json()["speakers"]

    assert (speaker["label"], speaker["sample"]) == ("Mira Holt", "<b>Hello</b> &amp; welcome.")


def test_a_source_that_is_not_a_transcript_has_no_speakers(client: TestClient) -> None:
    brief = _upload(client, "brief", b"Mira: a brief that looks like a turn.", "upload-0001")

    response = _speakers(client, brief["source_id"])

    assert response.status_code == 200
    assert response.json()["speakers"] == []


def test_lists_the_current_version_s_speakers(client: TestClient) -> None:
    transcript = _upload(client, "transcript", TRANSCRIPT, "upload-0001")
    revised = client.post(
        f"{SOURCES_URL}/{transcript['source_id']}/versions",
        files={"file": ("transcript.txt", b"Ana Lund: I will write it up.")},
        headers={"Idempotency-Key": "version-0001"},
    ).json()

    body = _speakers(client, transcript["source_id"]).json()

    assert body["source_version_id"] == revised["id"]
    assert [speaker["label"] for speaker in body["speakers"]] == ["Ana Lund"]


def test_a_transcript_stored_before_detection_gets_its_labels_on_first_read(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    client = make_client(seeded_database_url)
    transcript = _upload(client, "transcript", TRANSCRIPT, "upload-0001")
    with _session(seeded_database_url) as session:
        session.execute(delete(SpeakerLabelRecord))
        session.execute(update(SourceVersionRecord).values(speakers_detected_at=None))
        session.commit()

    first = _speakers(client, transcript["source_id"]).json()
    second = _speakers(client, transcript["source_id"]).json()

    assert [speaker["label"] for speaker in first["speakers"]] == ["Mira Holt", "Tomas Reed"]
    assert second == first
    with _session(seeded_database_url) as session:
        stored = session.scalar(select(func.count()).select_from(SpeakerLabelRecord))
    assert stored == 2


def test_any_role_on_the_project_can_read_speakers(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    client = make_client(seeded_database_url)
    transcript = _upload(client, "transcript", TRANSCRIPT, "upload-0001")

    for role in (Role.VIEWER, Role.APPROVER, Role.EDITOR):
        _set_roles(seeded_database_url, DEMO_PROJECT_ID, role)
        assert _speakers(client, transcript["source_id"]).status_code == 200


def test_another_project_s_source_and_an_unknown_source_are_not_found(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    other = _other_project(seeded_database_url)
    client = make_client(seeded_database_url)
    transcript = _upload(client, "transcript", TRANSCRIPT, "upload-0001")

    through_other = _speakers(client, transcript["source_id"], other)
    unknown = _speakers(client, str(new_id()))
    as_member = _speakers(client, transcript["source_id"])
    _set_roles(seeded_database_url, DEMO_PROJECT_ID)
    no_role = _speakers(client, transcript["source_id"])

    assert as_member.status_code == 200
    for response in (through_other, unknown, no_role):
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"
        assert "Mira" not in response.text
        assert "stand is taken" not in response.text
