"""Changing a member's role, removing a member and leaving a project (ADR 0019, ADR 0024).

Only an approver changes roles or removes someone else; any member may leave. A project always
keeps an approver. Two approvers acting at once cannot both take that away: the approvers'
memberships are locked while the change is checked, and the approvers are counted again after
the write, which also catches a database that does not lock rows (SQLite).
"""

from datetime import datetime
from typing import Protocol

from scopesteps.identity.application.users import UserReader
from scopesteps.identity.client import (
    ROLE_NAMES,
    MemberActivity,
    MemberEvent,
    Permission,
    ProjectAccess,
    Role,
    UserId,
)
from scopesteps.identity.domain.errors import LastApproverError, MemberChangedError
from scopesteps.identity.domain.invitation import check_keeps_an_approver, grantable_role
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectId


class MemberStore(Protocol):
    def role_by_member(self, project_id: ProjectId) -> dict[UserId, Role]:
        """Every member's role, with the project's approver memberships locked until the
        transaction ends (on databases that lock rows)."""
        ...

    def revision(self, project_id: ProjectId, user_id: UserId) -> int | None: ...

    def set_role(
        self,
        project_id: ProjectId,
        user_id: UserId,
        role: Role,
        now: datetime,
        *,
        expected_revision: int,
    ) -> bool:
        """Replace the member's role and move to the next revision. False, changing nothing, if
        the stored revision is not `expected_revision`."""
        ...

    def remove(self, project_id: ProjectId, user_id: UserId) -> None:
        """Delete the user's membership in the project. Records they authored stay."""
        ...

    def approver_count(self, project_id: ProjectId) -> int: ...


def change_role(
    members: MemberStore,
    users: UserReader,
    activity: MemberActivity,
    access: ProjectAccess,
    user_id: UserId,
    role: Role,
    *,
    expected_revision: int,
    now: datetime,
) -> None:
    """Give a member exactly `role`. Approver only; an approver may change their own role while
    another approver remains. Asking for the role they hold already changes nothing."""
    access.require(Permission.MANAGE_MEMBERS)
    chosen = grantable_role(role)
    current = members.role_by_member(access.project_id)
    held = current.get(user_id)
    if held is None:
        raise NotFoundError("Member not found")
    if held == chosen:
        return
    check_keeps_an_approver(current, user_id, chosen)
    if not members.set_role(
        access.project_id, user_id, chosen, now, expected_revision=expected_revision
    ):
        raise MemberChangedError(
            "This member's role was changed meanwhile. Reload the members and try again."
        )
    _still_has_an_approver(members, access.project_id)
    activity.record(
        MemberEvent(
            project_id=access.project_id,
            actor=access.actor,
            kind="member.roles_changed",
            summary=f"Changed {_name(users, user_id)}'s role to {ROLE_NAMES[chosen]}",
            occurred_at=now,
            member_id=user_id,
        )
    )


def remove_member(
    members: MemberStore,
    users: UserReader,
    activity: MemberActivity,
    access: ProjectAccess,
    user_id: UserId,
    now: datetime,
) -> None:
    """Take a member out of the project, or leave it when `user_id` is the actor. Access ends
    with the transaction; what they wrote keeps their name."""
    leaving = user_id == access.actor.user_id
    if leaving:
        access.require_member()
    else:
        access.require(Permission.MANAGE_MEMBERS)
    current = members.role_by_member(access.project_id)
    if user_id not in current:
        raise NotFoundError("Member not found")
    check_keeps_an_approver(current, user_id, None)
    name = _name(users, user_id)
    members.remove(access.project_id, user_id)
    _still_has_an_approver(members, access.project_id)
    activity.record(
        MemberEvent(
            project_id=access.project_id,
            actor=access.actor,
            kind="member.left" if leaving else "member.removed",
            summary=f"{name} left the project" if leaving else f"Removed {name} from the project",
            occurred_at=now,
            member_id=user_id,
        )
    )


def _still_has_an_approver(members: MemberStore, project_id: ProjectId) -> None:
    # The check above read the members before writing; a concurrent change that committed in
    # between is caught here, and the raise rolls this one back.
    if members.approver_count(project_id) == 0:
        raise LastApproverError(
            "A project needs at least one approver. Make someone else approver first."
        )


def _name(users: UserReader, user_id: UserId) -> str:
    user = users.get(user_id)
    return "A member" if user is None else user.display_name
