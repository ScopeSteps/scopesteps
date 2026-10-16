import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import make_url

from scopesteps.api.main import create_app
from scopesteps.api.migrations import upgrade_to_head
from scopesteps.api.seed import seed
from scopesteps.api.settings import Settings
from scopesteps.infrastructure.database import create_database_engine, create_session_factory

LOOPBACK_CLIENT = ("127.0.0.1", 50000)

ClientFactory = Callable[..., TestClient]


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
