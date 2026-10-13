from dataclasses import dataclass
from typing import Protocol

from scopesteps.identity.client import Actor, ProjectAccess, UserId
from scopesteps.identity.domain.user import Membership, User
from scopesteps.kernel.errors import UnauthenticatedError
from scopesteps.projects.client import ProjectId


class UserReader(Protocol):
    def get(self, user_id: UserId) -> User | None: ...

    def memberships(self, user_id: UserId) -> list[Membership]: ...


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
