from collections.abc import Callable
from uuid import UUID

from fastapi.testclient import TestClient

ClientFactory = Callable[..., TestClient]


def test_live_reports_ok(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_ok_when_schema_is_current(client: TestClient) -> None:
    assert client.get("/health/ready").status_code == 200


def test_ready_reports_outdated_schema_before_migrations(
    database_url: str, make_client: ClientFactory
) -> None:
    response = make_client(database_url).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["code"] == "SCHEMA_OUTDATED"


def test_ready_reports_unreachable_database(make_client: ClientFactory) -> None:
    client = make_client("postgresql+psycopg://nobody@127.0.0.1:1/missing")

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert response.json()["retryable"] is True


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    response = client.get("/health/live")

    assert UUID(response.headers["X-Request-ID"])


def test_client_supplied_request_id_is_echoed(client: TestClient) -> None:
    request_id = "019a3a5e-1111-7000-8000-000000000000"

    response = client.get("/health/live", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id
