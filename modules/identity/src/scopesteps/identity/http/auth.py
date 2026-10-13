from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from ipaddress import ip_address
from typing import Annotated

from fastapi import Depends, Request

from scopesteps.identity.application import users as use_cases
from scopesteps.identity.application.users import authenticate_local_user, get_project_access
from scopesteps.identity.client import (
    Actor,
    Memberships,
    ProjectAccess,
    ProjectAccessResolver,
    ProjectRoles,
    Role,
    UserId,
)
from scopesteps.identity.infrastructure.repository import SqlUserRepository
from scopesteps.infrastructure.http import SessionDep
from scopesteps.kernel.errors import PermissionDeniedError
from scopesteps.projects.client import ProjectId


@dataclass(frozen=True)
class LocalDevelopmentAuth:
    """Every request acts as one seeded user. Accepted only from loopback clients."""

    user_id: UserId


def get_current_actor(request: Request, session: SessionDep) -> Actor:
    auth: LocalDevelopmentAuth = request.app.state.auth
    if not _is_loopback(request):
        raise PermissionDeniedError(
            "Local development authentication accepts loopback clients only"
        )
    return authenticate_local_user(SqlUserRepository(session), auth.user_id)


def _is_loopback(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ip_address(request.client.host).is_loopback
    except ValueError:
        return False


CurrentActor = Annotated[Actor, Depends(get_current_actor)]


def resolve_project_access(
    project_id: ProjectId, actor: CurrentActor, session: SessionDep
) -> ProjectAccess:
    return get_project_access(SqlUserRepository(session), actor, project_id)


def resolve_project_access_resolver(
    actor: CurrentActor, session: SessionDep
) -> ProjectAccessResolver:
    users = SqlUserRepository(session)
    return lambda project_id: get_project_access(users, actor, project_id)


class SqlMemberships:
    def __init__(self, users: SqlUserRepository) -> None:
        self._users = users

    def of_user(self, user_id: UserId) -> list[ProjectRoles]:
        return use_cases.project_roles(self._users, user_id)

    def grant(
        self, user_id: UserId, project_id: ProjectId, roles: Collection[Role], now: datetime
    ) -> None:
        use_cases.grant_project_roles(self._users, user_id, project_id, roles, now)


def resolve_memberships(session: SessionDep) -> Memberships:
    return SqlMemberships(SqlUserRepository(session))
