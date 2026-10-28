import re
from collections.abc import Callable

from fastapi.testclient import TestClient

from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID

ClientFactory = Callable[..., TestClient]

# Reachable without an actor so a client can start and end a session (test_session_auth.py).
# Reached before anyone has a session: signing in and out, creating an account, confirming its
# email and opening an invitation.
PUBLIC_ROUTES = {
    ("post", "/api/v1/auth/sign-in"),
    ("post", "/api/v1/auth/sign-out"),
    ("post", "/api/v1/auth/sign-up"),
    ("post", "/api/v1/auth/verify-email"),
    ("post", "/api/v1/auth/resend-verification"),
    ("get", "/api/v1/invitations/{token}"),
    ("post", "/api/v1/invitations/{token}/sign-up"),
}


def test_local_reviewer_is_the_current_user(client: TestClient) -> None:
    response = client.get("/api/v1/me")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(LOCAL_REVIEWER_ID)
    assert body["display_name"] == "Local Reviewer"
    assert {(m["project_id"], m["role"]) for m in body["memberships"]} == {
        (str(DEMO_PROJECT_ID), "editor"),
        (str(DEMO_PROJECT_ID), "approver"),
    }


def test_local_auth_rejects_non_loopback_clients(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    client = make_client(seeded_database_url, client=("203.0.113.7", 50000))

    response = client.get("/api/v1/me")

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_local_auth_requires_the_seeded_reviewer(
    migrated_database_url: str, make_client: ClientFactory
) -> None:
    response = make_client(migrated_database_url).get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_every_module_route_requires_authentication(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    client = make_client(seeded_database_url, client=("203.0.113.7", 50000))
    paths: dict[str, dict[str, object]] = client.get("/openapi.json").json()["paths"]
    api_routes = [
        (method, path)
        for path, operations in paths.items()
        if path.startswith("/api/v1")
        for method in operations
        if (method, path) not in PUBLIC_ROUTES
    ]

    assert api_routes
    for method, path in api_routes:
        url = re.sub(r"\{[^}]+\}", str(DEMO_PROJECT_ID), path)
        assert client.request(method, url).status_code == 403, f"{method.upper()} {path}"
