"""What each project role may do (ADR 0024). Synthetic data only."""

from uuid import UUID

import pytest

from scopesteps.identity.client import (
    PERMISSION_ROLES,
    PROJECT_ROLES,
    Actor,
    Permission,
    ProjectAccess,
    Role,
    UserId,
    highest_role,
    permissions_of,
)
from scopesteps.kernel.errors import NotFoundError, PermissionDeniedError
from scopesteps.projects.client import ProjectId

ACTOR = Actor(UserId(UUID(int=1)), "Ann")
PROJECT = ProjectId(UUID(int=2))

# Written out by hand, from the decision, so a change to the table in the code shows up here.
VIEWER_CAN = {Permission.READ, Permission.DISCUSS}
EDITOR_CAN = VIEWER_CAN | {
    Permission.MANAGE_SOURCES,
    Permission.MANAGE_PEOPLE,
    Permission.USE_AGENT,
    Permission.EDIT_BACKLOG,
    Permission.REQUEST_CHANGES,
    Permission.MODERATE_DISCUSSIONS,
    Permission.RENAME_PROJECT,
}
APPROVER_CAN = EDITOR_CAN | {Permission.DECIDE_VERSIONS, Permission.MANAGE_MEMBERS}
EXPECTED = {Role.VIEWER: VIEWER_CAN, Role.EDITOR: EDITOR_CAN, Role.APPROVER: APPROVER_CAN}


def _access(role: Role | None) -> ProjectAccess:
    return ProjectAccess(ACTOR, PROJECT, role)


def test_every_permission_has_a_lowest_role() -> None:
    assert set(PERMISSION_ROLES) == set(Permission)
    assert set(PERMISSION_ROLES.values()) <= set(PROJECT_ROLES)


@pytest.mark.parametrize("role", PROJECT_ROLES)
def test_each_role_has_exactly_its_permissions(role: Role) -> None:
    assert permissions_of(role) == EXPECTED[role]
    assert _access(role).permissions == EXPECTED[role]


@pytest.mark.parametrize(
    ("lower", "higher"), [(Role.VIEWER, Role.EDITOR), (Role.EDITOR, Role.APPROVER)]
)
def test_a_higher_role_can_do_everything_a_lower_one_can(lower: Role, higher: Role) -> None:
    assert permissions_of(lower) < permissions_of(higher)


@pytest.mark.parametrize("role", PROJECT_ROLES)
@pytest.mark.parametrize("permission", list(Permission))
def test_require_allows_exactly_what_the_role_may_do(role: Role, permission: Permission) -> None:
    access = _access(role)

    if permission in EXPECTED[role]:
        access.require(permission)
        assert access.can(permission)
    else:
        with pytest.raises(PermissionDeniedError) as refused:
            access.require(permission)
        assert not access.can(permission)
        assert refused.value.details == {"required_role": PERMISSION_ROLES[permission].value}


@pytest.mark.parametrize(
    ("permission", "message"),
    [
        (Permission.USE_AGENT, "Only an Editor or Approver on this project can do this."),
        (Permission.DECIDE_VERSIONS, "Only an Approver on this project can do this."),
    ],
)
def test_a_refusal_names_the_roles_that_may(permission: Permission, message: str) -> None:
    with pytest.raises(PermissionDeniedError) as refused:
        _access(Role.VIEWER).require(permission)

    assert refused.value.message == message


@pytest.mark.parametrize("role", [None, Role.WORKSPACE_ADMIN, Role.INTEGRATION_ADMIN])
def test_a_non_member_is_told_the_project_does_not_exist(role: Role | None) -> None:
    access = _access(role)

    assert not access.is_member
    assert access.permissions == frozenset()
    with pytest.raises(NotFoundError):
        access.require(Permission.READ)
    with pytest.raises(NotFoundError):
        access.member_role()


@pytest.mark.parametrize(
    ("roles", "highest"),
    [
        ([], None),
        ([Role.VIEWER], Role.VIEWER),
        ([Role.EDITOR, Role.APPROVER], Role.APPROVER),
        ([Role.APPROVER, Role.VIEWER], Role.APPROVER),
        ([Role.WORKSPACE_ADMIN], None),
    ],
)
def test_the_highest_project_role_wins(roles: list[Role], highest: Role | None) -> None:
    assert highest_role(roles) == highest
