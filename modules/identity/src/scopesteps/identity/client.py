from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, NewType, Protocol
from uuid import UUID

from scopesteps.kernel.errors import NotFoundError, PermissionDeniedError
from scopesteps.projects.client import ProjectId

UserId = NewType("UserId", UUID)


class Role(StrEnum):
    VIEWER = "viewer"
    EDITOR = "editor"
    APPROVER = "approver"
    INTEGRATION_ADMIN = "integration_admin"
    WORKSPACE_ADMIN = "workspace_admin"


@dataclass(frozen=True)
class Actor:
    """The authenticated user a request acts on behalf of."""

    user_id: UserId
    display_name: str


@dataclass(frozen=True)
class ProjectAccess:
    """The roles the current actor holds in the project a request addresses."""

    actor: Actor
    project_id: ProjectId
    roles: frozenset[Role]

    def require_member(self) -> None:
        """A project the actor has no role in is reported exactly like one that does not exist."""
        if not self.roles:
            raise NotFoundError("Project not found")

    def require_role(self, role: Role) -> None:
        self.require_member()
        if role not in self.roles:
            raise PermissionDeniedError(
                f"This action requires the {role.value} role on the project"
            )

    def require_any_role(self, *roles: Role) -> None:
        self.require_member()
        if self.roles.isdisjoint(roles):
            names = " or ".join(role.value for role in roles)
            raise PermissionDeniedError(f"This action requires the {names} role on the project")


@dataclass(frozen=True)
class ProjectRoles:
    """Every role one user holds in one project. Never empty."""

    project_id: ProjectId
    roles: frozenset[Role]


class Memberships(Protocol):
    """Project roles, read and granted in the request's transaction. Performs no access check:
    the caller decides whose roles may be read and who may be granted what."""

    def of_user(self, user_id: UserId) -> list[ProjectRoles]:
        """The projects the user is a member of, each with all of the user's roles in it."""
        ...

    def grant(
        self, user_id: UserId, project_id: ProjectId, roles: Collection[Role], now: datetime
    ) -> None:
        """Give the user the roles they do not hold yet. The caller commits."""
        ...


MemberEventKind = Literal[
    "member.invited",
    "invitation.link_created",
    "invitation.emailed",
    "invitation.accepted",
    "invitation.cancelled",
    "member.roles_changed",
    "member.removed",
    "member.left",
]


@dataclass(frozen=True)
class MemberEvent:
    """A change to who belongs to a project, for its activity log. `summary` names people by
    display name and roles by name; never an email address or a token."""

    project_id: ProjectId
    actor: Actor
    kind: MemberEventKind
    summary: str
    occurred_at: datetime
    member_id: UserId | None = None
    invitation_id: UUID | None = None


class MemberActivity(Protocol):
    def record(self, event: MemberEvent) -> None:
        """Record in the request's transaction, committed or rolled back with the change."""
        ...


def get_member_activity() -> MemberActivity:
    """FastAPI dependency through which membership changes reach the activity log.

    `audit` builds on this module's client, so identity cannot import it; the composition root
    binds `audit`'s recorder with `app.dependency_overrides`.
    """
    raise RuntimeError("get_member_activity is not bound to the activity log")


def get_actor() -> Actor:
    """FastAPI dependency for routes that address no project, such as the project list.

    Bound by the composition root like `get_project_access`.
    """
    raise RuntimeError("get_actor is not bound to identity's authentication")


def get_memberships() -> Memberships:
    """FastAPI dependency for the module that lists and creates projects. Bound by the
    composition root like `get_project_access`."""
    raise RuntimeError("get_memberships is not bound to identity's implementation")


def get_project_access() -> ProjectAccess:
    """FastAPI dependency for project-scoped routes in any module.

    Identity owns the implementation; the composition root binds it with
    `app.dependency_overrides`, so modules never import identity's internals.
    """
    raise RuntimeError("get_project_access is not bound to identity's resolver")


ProjectAccessResolver = Callable[[ProjectId], ProjectAccess]


def get_project_access_resolver() -> ProjectAccessResolver:
    """FastAPI dependency for routes that address a resource by its own ID, such as /runs/{id}.

    The route loads the resource, then resolves access to the project it belongs to. Bound by the
    composition root like `get_project_access`.
    """
    raise RuntimeError("get_project_access_resolver is not bound to identity's resolver")
