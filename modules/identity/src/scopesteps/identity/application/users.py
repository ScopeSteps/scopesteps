from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from scopesteps.identity.client import Actor, ProjectAccess, ProjectRoles, Role, UserId
from scopesteps.identity.domain.user import Membership, User
from scopesteps.kernel.errors import UnauthenticatedError
from scopesteps.projects.client import ProjectId


class UserReader(Protocol):
    def get(self, user_id: UserId) -> User | None: ...

    def memberships(self, user_id: UserId) -> list[Membership]: ...


class MembershipWriter(UserReader, Protocol):
    def add_membership(self, membership: Membership) -> None:
        """Insert within the caller's transaction; the caller commits."""
        ...


@dataclass(frozen=True)
class UserProfile:
    user: User
    memberships: list[Membership]


def authenticate_local_user(users: UserReader, user_id: UserId) -> Actor:
    user = users.get(user_id)
    if user is None:
        raise UnauthenticatedError("The local reviewer does not exist. Run `just seed`.")
    return Actor(user_id=user.id, display_name=user.display_name)


def get_user_profile(users: UserReader, actor: Actor) -> UserProfile:
    user = users.get(actor.user_id)
    if user is None:
        raise UnauthenticatedError("The authenticated user no longer exists")
    return UserProfile(user=user, memberships=users.memberships(user.id))


def get_project_access(users: UserReader, actor: Actor, project_id: ProjectId) -> ProjectAccess:
    roles = frozenset(
        membership.role
        for membership in users.memberships(actor.user_id)
        if membership.project_id == project_id
    )
    return ProjectAccess(actor=actor, project_id=project_id, roles=roles)


def project_roles(users: UserReader, user_id: UserId) -> list[ProjectRoles]:
    roles: dict[ProjectId, set[Role]] = {}
    for membership in users.memberships(user_id):
        roles.setdefault(membership.project_id, set()).add(membership.role)
    return [ProjectRoles(project_id, frozenset(held)) for project_id, held in roles.items()]


def grant_project_roles(
    users: MembershipWriter,
    user_id: UserId,
    project_id: ProjectId,
    roles: Collection[Role],
    now: datetime,
) -> None:
    held = {m.role for m in users.memberships(user_id) if m.project_id == project_id}
    for role in sorted(set(roles) - held):
        users.add_membership(
            Membership(user_id=user_id, project_id=project_id, role=role, granted_at=now)
        )
