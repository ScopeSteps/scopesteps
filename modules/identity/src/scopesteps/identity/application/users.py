from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from scopesteps.identity.client import (
    Actor,
    ProjectAccess,
    ProjectMembership,
    Role,
    UserId,
    WaitingByRole,
    highest_role,
    role_includes,
)
from scopesteps.identity.domain.profile import Profile, ProfileChangedError, normalize_profile
from scopesteps.identity.domain.user import Membership, ProjectMember, User
from scopesteps.kernel.errors import UnauthenticatedError
from scopesteps.projects.client import ProjectId

# Enough to pick from as you type; a longer list means typing another letter.
MEMBER_SEARCH_LIMIT = 8


class UserReader(Protocol):
    def get(self, user_id: UserId) -> User | None: ...

    def memberships(self, user_id: UserId) -> list[Membership]: ...


class MembershipWriter(UserReader, Protocol):
    def add_membership(self, membership: Membership) -> None:
        """Insert within the caller's transaction; the caller commits."""
        ...

    def set_membership_role(self, user_id: UserId, project_id: ProjectId, role: Role) -> None:
        """Change the role of an existing membership; the caller commits."""
        ...


class ProfileWriter(UserReader, Protocol):
    def update_profile(self, user_id: UserId, profile: Profile, *, expected_revision: int) -> bool:
        """Save the profile and move to the next revision. False, changing nothing, if the stored
        revision is not `expected_revision`. The caller commits."""
        ...


class MemberReader(Protocol):
    def project_members(self, project_id: ProjectId) -> list[ProjectMember]:
        """Everyone with a role in the project, ordered by name."""
        ...


@dataclass(frozen=True)
class UpdateProfile:
    display_name: str
    job_title: str
    about: str
    expected_revision: int


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


def update_profile(users: ProfileWriter, actor: Actor, command: UpdateProfile) -> UserProfile:
    """Save the actor's own profile; nobody edits another user's profile."""
    profile = normalize_profile(command.display_name, command.job_title, command.about)
    user = users.get(actor.user_id)
    if user is None:
        raise UnauthenticatedError("The authenticated user no longer exists")
    # A retry of a save that already landed changes nothing, so it succeeds without a new
    # revision instead of reporting its own earlier save as a conflict.
    if Profile(user.display_name, user.job_title, user.about) == profile:
        return UserProfile(user=user, memberships=users.memberships(user.id))
    if not users.update_profile(user.id, profile, expected_revision=command.expected_revision):
        raise ProfileChangedError(
            "Your profile was changed somewhere else. Reload it and make your changes again."
        )
    return get_user_profile(users, actor)


def list_project_members(members: MemberReader, access: ProjectAccess) -> list[ProjectMember]:
    """Any member may see who else is in the project, so the app can name who did what."""
    access.require_member()
    return members.project_members(access.project_id)


@dataclass(frozen=True)
class TeamMember:
    member: ProjectMember
    waiting: int
    """What waits in the project for someone with the member's role, as their home page counts
    it. Work is waiting on a role, not assigned to a person: two editors see the same items."""


def list_team(
    members: MemberReader, waiting_by_role: WaitingByRole, access: ProjectAccess
) -> list[TeamMember]:
    """The members, by name, each with what waits for them. Any member may read it."""
    found = list_project_members(members, access)
    waiting = waiting_by_role(access.project_id)
    return [TeamMember(member, waiting.get(member.role, 0)) for member in found]


def search_project_members(
    members: MemberReader, access: ProjectAccess, query: str
) -> list[ProjectMember]:
    """Members whose name contains `query`, for the mention picker. Any member may search."""
    access.require_member()
    wanted = query.strip().casefold()
    matches = [
        member
        for member in members.project_members(access.project_id)
        if wanted in member.display_name.casefold()
    ]
    return matches[:MEMBER_SEARCH_LIMIT]


def get_project_access(users: UserReader, actor: Actor, project_id: ProjectId) -> ProjectAccess:
    return ProjectAccess(
        actor=actor, project_id=project_id, role=_role_in(users, actor.user_id, project_id)
    )


def project_memberships(users: UserReader, user_id: UserId) -> list[ProjectMembership]:
    by_project: dict[ProjectId, list[Role]] = {}
    for membership in users.memberships(user_id):
        by_project.setdefault(membership.project_id, []).append(membership.role)
    held = ((project_id, highest_role(roles)) for project_id, roles in by_project.items())
    return [ProjectMembership(project_id, role) for project_id, role in held if role is not None]


def grant_project_role(
    users: MembershipWriter,
    user_id: UserId,
    project_id: ProjectId,
    role: Role,
    now: datetime,
) -> None:
    """Make the user a member with `role`, or raise their role to it. Never lowers a role."""
    held = _role_in(users, user_id, project_id)
    if held is None:
        users.add_membership(
            Membership(user_id=user_id, project_id=project_id, role=role, granted_at=now)
        )
    elif not role_includes(held, role):
        users.set_membership_role(user_id, project_id, role)


def _role_in(users: UserReader, user_id: UserId, project_id: ProjectId) -> Role | None:
    # One row per member and project; the highest is taken so a stray row never grants less.
    return highest_role([m.role for m in users.memberships(user_id) if m.project_id == project_id])
