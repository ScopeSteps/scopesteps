from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
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


PROJECT_ROLES: tuple[Role, ...] = (Role.VIEWER, Role.EDITOR, Role.APPROVER)
"""The roles a project member can hold, lowest first. A member holds exactly one, and each can do
everything the roles before it can (ADR 0024). The admin roles are never held in a project."""

ROLE_NAMES: Mapping[Role, str] = MappingProxyType(
    {Role.VIEWER: "Viewer", Role.EDITOR: "Editor", Role.APPROVER: "Approver"}
)


class Permission(StrEnum):
    """Something a project member may do. Modules check one of these, never a role name."""

    READ = "read"
    """See the project, its sources, backlogs, runs and conversation."""
    DISCUSS = "discuss"
    """Start and reply to discussions, and close the ones you started."""
    MANAGE_SOURCES = "manage_sources"
    """Upload sources, add new versions and remove them."""
    MANAGE_PEOPLE = "manage_people"
    """Correct the people in sources, assign speakers and confirm source rights."""
    USE_AGENT = "use_agent"
    """Chat with the agent, start, continue and stop runs, and answer its questions."""
    EDIT_BACKLOG = "edit_backlog"
    """Edit backlog items, answer open decisions and accept or reject chat suggestions."""
    REQUEST_CHANGES = "request_changes"
    """Request a change to the approved backlog, from the chat or from a discussion."""
    MODERATE_DISCUSSIONS = "moderate_discussions"
    """Close anyone's discussion."""
    RENAME_PROJECT = "rename_project"
    DECIDE_VERSIONS = "decide_versions"
    """Approve or reject a backlog version, and accept or reject suggestions on a draft."""
    MANAGE_MEMBERS = "manage_members"
    """Invite people, see pending invitations, change roles and remove members."""


PERMISSION_ROLES: Mapping[Permission, Role] = MappingProxyType(
    {
        Permission.READ: Role.VIEWER,
        Permission.DISCUSS: Role.VIEWER,
        Permission.MANAGE_SOURCES: Role.EDITOR,
        Permission.MANAGE_PEOPLE: Role.EDITOR,
        Permission.USE_AGENT: Role.EDITOR,
        Permission.EDIT_BACKLOG: Role.EDITOR,
        Permission.REQUEST_CHANGES: Role.EDITOR,
        Permission.MODERATE_DISCUSSIONS: Role.EDITOR,
        Permission.RENAME_PROJECT: Role.EDITOR,
        Permission.DECIDE_VERSIONS: Role.APPROVER,
        Permission.MANAGE_MEMBERS: Role.APPROVER,
    }
)
"""The lowest role that may do each thing: the single place project permissions are decided."""


def role_includes(role: Role | None, lowest: Role) -> bool:
    """`role` is `lowest` or a role above it. No role, or an admin role, includes nothing."""
    if role not in PROJECT_ROLES or lowest not in PROJECT_ROLES:
        return False
    return PROJECT_ROLES.index(role) >= PROJECT_ROLES.index(lowest)


def permissions_of(role: Role | None) -> frozenset[Permission]:
    return frozenset(p for p, lowest in PERMISSION_ROLES.items() if role_includes(role, lowest))


def highest_role(roles: Collection[Role]) -> Role | None:
    """The highest project role among `roles`, or None when there is none."""
    held = [role for role in PROJECT_ROLES if role in roles]
    return held[-1] if held else None


@dataclass(frozen=True)
class Actor:
    """The authenticated user a request acts on behalf of."""

    user_id: UserId
    display_name: str


@dataclass(frozen=True)
class ProjectAccess:
    """The role the current actor holds in the project a request addresses; None for a
    non-member."""

    actor: Actor
    project_id: ProjectId
    role: Role | None

    @property
    def is_member(self) -> bool:
        return self.role in PROJECT_ROLES

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_of(self.role)

    def can(self, permission: Permission) -> bool:
        return role_includes(self.role, PERMISSION_ROLES[permission])

    def require_member(self) -> None:
        """A project the actor has no role in is reported exactly like one that does not exist."""
        if not self.is_member:
            raise NotFoundError("Project not found")

    def member_role(self) -> Role:
        """The actor's role; a non-member gets the same not-found as `require_member`."""
        if self.role is None or not self.is_member:
            raise NotFoundError("Project not found")
        return self.role

    def require(self, permission: Permission) -> None:
        self.require_member()
        if not self.can(permission):
            needed = PERMISSION_ROLES[permission]
            raise PermissionDeniedError(
                f"{_needs(needed)} on this project can do this.",
                details={"required_role": needed.value},
            )


def _needs(role: Role) -> str:
    """ "Only an Editor or Approver": the role and every role above it."""
    names = " or ".join(ROLE_NAMES[r] for r in PROJECT_ROLES[PROJECT_ROLES.index(role) :])
    return f"Only {'an' if names[0] in 'AEIOU' else 'a'} {names}"


@dataclass(frozen=True)
class ProjectMembership:
    """The one role a user holds in one project."""

    project_id: ProjectId
    role: Role


class Memberships(Protocol):
    """Project roles, read and granted in the request's transaction. Performs no access check:
    the caller decides whose roles may be read and who may be granted what."""

    def of_user(self, user_id: UserId) -> list[ProjectMembership]:
        """The projects the user is a member of, each with the user's role in it."""
        ...

    def grant(self, user_id: UserId, project_id: ProjectId, role: Role, now: datetime) -> None:
        """Make the user a member with `role`, or raise their role to it; never lowers a role.
        The caller commits."""
        ...


@dataclass(frozen=True)
class DirectoryMember:
    """A project member as other modules see them: no email."""

    user_id: UserId
    display_name: str
    role: Role


class UserDirectory(Protocol):
    """Who people are, read in the caller's transaction. Performs no access check: the caller
    checks the actor's access first, and keeps addresses out of responses and logs."""

    def members(self, project_id: ProjectId) -> list[DirectoryMember]:
        """Everyone with a role in the project now, ordered by name."""
        ...

    def display_names(self, user_ids: Collection[UserId]) -> dict[UserId, str]:
        """Current names, for members and former members alike."""
        ...

    def email_addresses(self, user_ids: Collection[UserId]) -> dict[UserId, str]: ...

    def project_ids(self, user_id: UserId) -> frozenset[ProjectId]:
        """The projects the user is a member of now."""
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


def get_user_directory() -> UserDirectory:
    """FastAPI dependency for modules that name, or email, people. Bound by the composition root
    like `get_project_access`."""
    raise RuntimeError("get_user_directory is not bound to identity's implementation")


WaitingByRole = Callable[[ProjectId], Mapping[Role, int]]
"""How many things in the project wait for a member holding each project role, counted the way
the home page counts them, so the two never disagree. A role nothing waits for may be absent.
Performs no access check: the caller checks the actor's access to the project first."""


def get_waiting_by_role() -> WaitingByRole:
    """FastAPI dependency for the members list. The modules that hold the waiting work build on
    this one, so the composition root binds the projects module's count."""
    raise RuntimeError("get_waiting_by_role is not bound to the projects module's count")


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
