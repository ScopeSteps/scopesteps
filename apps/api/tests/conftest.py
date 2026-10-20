import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import make_url

from scopesteps.api.main import create_app
from scopesteps.api.migrations import upgrade_to_head
from scopesteps.api.seed import DEMO_PROJECT_ID, seed
from scopesteps.api.settings import Settings
from scopesteps.infrastructure.database import create_database_engine, create_session_factory

LOOPBACK_CLIENT = ("127.0.0.1", 50000)

ClientFactory = Callable[..., TestClient]
SpeakerConfirmer = Callable[..., None]

# Who the room-booking fixture's speakers are, as `evals/datasets/dev/campus-room-booking`
# confirms them. A label not listed here becomes a participant named after the label.
ROOM_BOOKING_SPEAKERS = {
    "dana": ("Dana Ruiz", "Sponsor"),
    "sam": ("Sam Okafor", "End-user representative"),
    "priya": ("Priya Nair", "Developer"),
    "alex": ("Alex Kim", "Product owner"),
}


@pytest.fixture(autouse=True)
def isolate_from_local_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path}/scopesteps.db"


@pytest.fixture(scope="session")
def migrated_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A database at head, migrated once per test session (per worker under xdist): running every
    migration takes seconds, copying the result takes a millisecond."""
    path = tmp_path_factory.mktemp("template") / "scopesteps.db"
    upgrade_to_head(f"sqlite:///{path}")
    return path


@pytest.fixture
def migrated_database_url(database_url: str, migrated_template: Path) -> str:
    # The backup API copies a WAL-mode database consistently, which a file copy may not.
    target_path = make_url(database_url).database or ""
    with (
        closing(sqlite3.connect(migrated_template)) as source,
        closing(sqlite3.connect(target_path)) as target,
    ):
        source.backup(target)
    return database_url


@pytest.fixture
def seeded_database_url(migrated_database_url: str) -> str:
    engine = create_database_engine(migrated_database_url)
    with create_session_factory(engine)() as session:
        seed(session)
    engine.dispose()
    return migrated_database_url


@pytest.fixture
def make_client() -> Iterator[ClientFactory]:
    clients: list[TestClient] = []

    def factory(
        database_url: str, client: tuple[str, int] = LOOPBACK_CLIENT, **settings: object
    ) -> TestClient:
        # Acts as the Local Reviewer unless a test asks for `auth_mode="session"`.
        values = {"app_env": "test", "auth_mode": "local", "database_url": database_url, **settings}
        app = create_app(Settings.model_validate(values))
        test_client = TestClient(app, client=client).__enter__()
        clients.append(test_client)
        return test_client

    yield factory
    for test_client in clients:
        test_client.__exit__(None, None, None)


@pytest.fixture
def client(seeded_database_url: str, make_client: ClientFactory) -> TestClient:
    return make_client(seeded_database_url)


def _confirm_speakers(client: TestClient, project_id: str = str(DEMO_PROJECT_ID)) -> None:
    """Answer for every speaker nobody has confirmed yet, as an editor does in Who's who before
    a draft run may start (ADR 0015). Answers already given are sent back unchanged."""
    base = f"/api/v1/projects/{project_id}"
    for transcript in client.get(f"{base}/speakers").json()["transcripts"]:
        if all(speaker["status"] != "unconfirmed" for speaker in transcript["speakers"]):
            continue
        answers: list[dict[str, object]] = []
        for speaker in transcript["speakers"]:
            if speaker["status"] == "not_a_person":
                answers.append({"label_key": speaker["key"], "choice": "not_a_person"})
            elif speaker["person_id"] is not None:
                answers.append(
                    {
                        "label_key": speaker["key"],
                        "choice": "link",
                        "person_id": speaker["person_id"],
                    }
                )
            else:
                name, role = ROOM_BOOKING_SPEAKERS.get(speaker["key"], (speaker["label"], None))
                answers.append(
                    {
                        "label_key": speaker["key"],
                        "choice": "new",
                        "name": name,
                        "meeting_role": role,
                    }
                )
        saved = client.put(
            f"{base}/sources/{transcript['source_id']}/speakers",
            json={"expected_revision": transcript["revision"], "speakers": answers},
            headers={
                "Idempotency-Key": f"confirm-{transcript['source_id']}-{transcript['revision']}"
            },
        )
        assert saved.status_code == 200, saved.text


@pytest.fixture
def confirm_speakers() -> SpeakerConfirmer:
    return _confirm_speakers
