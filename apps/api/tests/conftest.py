from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture
def migrated_database_url(database_url: str) -> str:
    upgrade_to_head(database_url)
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

    def factory(database_url: str, client: tuple[str, int] = LOOPBACK_CLIENT) -> TestClient:
        app = create_app(Settings(app_env="test", database_url=database_url))
        test_client = TestClient(app, client=client).__enter__()
        clients.append(test_client)
        return test_client

    yield factory
    for test_client in clients:
        test_client.__exit__(None, None, None)


@pytest.fixture
def client(seeded_database_url: str, make_client: ClientFactory) -> TestClient:
    return make_client(seeded_database_url)
