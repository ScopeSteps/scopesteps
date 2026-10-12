from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from scopesteps.api.database import get_engine
from scopesteps.api.main import create_app
from scopesteps.api.settings import Settings


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(Settings(app_env="test"))
    app.dependency_overrides[get_engine] = lambda: create_engine("sqlite://")
    with TestClient(app) as test_client:
        yield test_client


def test_live_reports_ok(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_ok_when_database_reachable(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200


def test_ready_reports_unavailable_when_database_unreachable() -> None:
    app = create_app(Settings(app_env="test"))
    app.dependency_overrides[get_engine] = lambda: create_engine(
        "postgresql+psycopg://nobody@127.0.0.1:1/missing"
    )

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
