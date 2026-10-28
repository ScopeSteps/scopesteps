"""The rules behind invitations and member roles, without a database. Synthetic data only."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from scopesteps.identity.application.emails import invitation_email, role_names
from scopesteps.identity.application.limits import Bucket, Limit, take_attempt
from scopesteps.identity.client import Role, UserId
from scopesteps.identity.domain.errors import (
    LastApproverError,
    RolesInvalidError,
    TooManyAttemptsError,
)
from scopesteps.identity.domain.invitation import check_keeps_an_approver, grantable_roles
from scopesteps.identity.domain.tokens import hash_link_token, new_link_token
from scopesteps.identity.domain.user import is_valid_email

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
ANN = UserId(UUID(int=1))
BEN = UserId(UUID(int=2))


@pytest.mark.parametrize(
    ("roles", "valid"),
    [
        ([Role.VIEWER], True),
        ([Role.EDITOR, Role.APPROVER], True),
        ([], False),
        ([Role.WORKSPACE_ADMIN], False),
        ([Role.VIEWER, Role.INTEGRATION_ADMIN], False),
    ],
)
def test_only_viewer_editor_and_approver_can_be_given(roles: list[Role], valid: bool) -> None:
    if valid:
        assert grantable_roles(roles) == frozenset(roles)
    else:
        with pytest.raises(RolesInvalidError):
            grantable_roles(roles)


def test_a_project_keeps_an_approver() -> None:
    both = {ANN: frozenset({Role.APPROVER}), BEN: frozenset({Role.APPROVER, Role.EDITOR})}
    only_ann = {ANN: frozenset({Role.APPROVER}), BEN: frozenset({Role.EDITOR})}

    check_keeps_an_approver(both, ANN, frozenset())
    check_keeps_an_approver(only_ann, BEN, frozenset())
    with pytest.raises(LastApproverError):
        check_keeps_an_approver(only_ann, ANN, frozenset())
    with pytest.raises(LastApproverError):
        check_keeps_an_approver(only_ann, ANN, frozenset({Role.EDITOR}))


class Attempts:
    def __init__(self) -> None:
        self.at: list[tuple[str, str, datetime]] = []

    def count(self, bucket: Bucket, key_hash: str, since: datetime) -> int:
        return sum(1 for b, k, at in self.at if (b, k) == (bucket, key_hash) and at > since)

    def add(self, bucket: Bucket, key_hash: str, at: datetime) -> None:
        self.at.append((bucket, key_hash, at))


def test_a_limit_counts_attempts_in_a_rolling_window_and_stores_no_key() -> None:
    attempts = Attempts()
    limit = Limit("sign_up_email", 2, timedelta(hours=1))

    take_attempt(attempts, limit, "a@example.test", NOW)
    take_attempt(attempts, limit, "a@example.test", NOW + timedelta(minutes=1))
    with pytest.raises(TooManyAttemptsError):
        take_attempt(attempts, limit, "a@example.test", NOW + timedelta(minutes=2))
    take_attempt(attempts, limit, "b@example.test", NOW + timedelta(minutes=2))
    take_attempt(attempts, limit, "a@example.test", NOW + timedelta(minutes=61))

    assert all("@" not in key for _, key, _ in attempts.at)


def test_link_tokens_are_long_random_and_stored_only_as_a_hash() -> None:
    first, second = new_link_token(), new_link_token()

    assert len(first) >= 43
    assert first != second
    assert hash_link_token(first) != first
    assert len(hash_link_token(first)) == 64


@pytest.mark.parametrize(
    ("email", "valid"),
    [("ann@example.test", True), ("ann@example", False), ("ann example.test", False), ("", False)],
)
def test_an_email_must_look_like_one(email: str, valid: bool) -> None:
    assert is_valid_email(email) is valid


def test_role_names_read_as_a_list() -> None:
    assert role_names({Role.APPROVER}) == "Approver"
    assert role_names({Role.APPROVER, Role.VIEWER}) == "Viewer and Approver"
    assert role_names({Role.EDITOR, Role.APPROVER, Role.VIEWER}) == "Viewer, Editor and Approver"


def test_an_invitation_email_escapes_names_in_its_html() -> None:
    message = invitation_email(
        to="ben@example.test",
        inviter='Ann "<script>"',
        project="R&D <Rooms>",
        roles={Role.EDITOR},
        link="https://app.example.test/invite/abc",
        expires_at=NOW,
    )

    assert "&lt;script&gt;" in message.html
    assert "R&amp;D &lt;Rooms&gt;" in message.html
    assert "<script>" not in message.html
    assert "expires on 27 October 2026 at 09:00 UTC" in message.text
