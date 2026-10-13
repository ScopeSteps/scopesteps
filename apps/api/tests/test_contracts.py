import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scopesteps.api.main import create_app
from scopesteps.api.modules import MODULE_NAMES, register_all_tables
from scopesteps.api.seed import DEMO_PROJECT_ID
from scopesteps.api.settings import Settings
from scopesteps.infrastructure.database import Base

REPO_ROOT = Path(__file__).resolve().parents[3]

PLANNED_FLOWS = {
    ("post", "/api/v1/projects/{project_id}/sources"),
    ("get", "/api/v1/projects/{project_id}/sources/{source_version_id}/blocks"),
    ("post", "/api/v1/projects/{project_id}/runs"),
    ("get", "/api/v1/runs/{run_id}"),
    ("post", "/api/v1/runs/{run_id}/advance"),
    ("post", "/api/v1/runs/{run_id}/answers"),
    ("post", "/api/v1/runs/{run_id}/cancel"),
    ("get", "/api/v1/projects/{project_id}/backlogs/{version_id}"),
    ("patch", "/api/v1/backlogs/{version_id}/items/{item_id}"),
    ("post", "/api/v1/backlogs/{version_id}/review"),
    ("post", "/api/v1/backlogs/{version_id}/approve"),
    ("post", "/api/v1/backlogs/{version_id}/reject"),
    ("get", "/api/v1/backlogs/{version_id}/change-set"),
    ("get", "/api/v1/backlogs/{version_id}/export"),
}


@pytest.fixture(scope="module")
def openapi() -> dict[str, Any]:
    return create_app(Settings(app_env="test", database_url="sqlite://")).openapi()


def test_openapi_covers_every_planned_flow(
    openapi: dict[str, Any],
) -> None:
    documented = {(method, path) for path, ops in openapi["paths"].items() for method in ops}

    assert documented >= PLANNED_FLOWS


def test_mutating_commands_require_an_idempotency_key(
    openapi: dict[str, Any],
) -> None:
    commands = [(method, path) for method, path in PLANNED_FLOWS if method != "get"]

    for method, path in commands:
        parameters = openapi["paths"][path][method].get("parameters", [])
        assert "Idempotency-Key" in {p["name"] for p in parameters}, f"{method.upper()} {path}"


def test_committed_contract_matches_the_api(
    openapi: dict[str, Any],
) -> None:
    committed = json.loads((REPO_ROOT / "contracts" / "openapi.json").read_text())

    assert committed == openapi, "Run `just contract` and commit the result"


def test_unimplemented_flows_return_501_with_the_error_envelope(client: TestClient) -> None:
    response = client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/backlogs/{DEMO_PROJECT_ID}")

    assert response.status_code == 501
    body = response.json()
    assert body["code"] == "NOT_IMPLEMENTED"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["retryable"] is False


def test_invalid_requests_return_422_with_the_error_envelope(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/projects/{DEMO_PROJECT_ID}/runs",
        json={"mode": "change", "source_version_ids": []},
        headers={"Idempotency-Key": "test-key-0001"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_every_table_is_prefixed_with_its_owning_module() -> None:
    register_all_tables()

    for mapper in Base.registry.mappers:
        owner = mapper.class_.__module__.split(".")[1]
        assert owner in MODULE_NAMES
        table_name: str = mapper.class_.__tablename__
        assert table_name.startswith(f"{owner}_"), table_name
