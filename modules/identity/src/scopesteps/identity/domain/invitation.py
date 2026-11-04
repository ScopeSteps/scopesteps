"""Invitations to a project and the rules about who holds which role in it (ADR 0019)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import NewType
from uuid import UUID

from scopesteps.identity.client import PROJECT_ROLES, Role, UserId
from scopesteps.identity.domain.errors import LastApproverError, RoleInvalidError
from scopesteps.projects.client import ProjectId

InvitationId = NewType("InvitationId", UUID)


def grantable_role(role: Role) -> Role:
    """The workspace and integration admin roles are never given per project from the app."""
    if role not in PROJECT_ROLES:
        raise RoleInvalidError("Choose Viewer, Editor or Approver")
    return role


@dataclass(frozen=True)
class Invitation:
    """A personal invitation for one email address to join one project with a role. Only the
    hash of its link's token is kept; making a new link replaces it."""

    id: InvitationId
    project_id: ProjectId
    email: str
    role: Role
    invited_by: UserId
    token_hash: str
    expires_at: datetime
    created_at: datetime
    accepted_at: datetime | None = None

    def is_open(self, now: datetime) -> bool:
        """Its link still works: not accepted and not expired. A cancelled one no longer exists."""
        return self.accepted_at is None and now < self.expires_at


def check_keeps_an_approver(
    role_by_member: Mapping[UserId, Role],
    member: UserId,
    role_after: Role | None,
) -> None:
    """A project always keeps at least one approver: refuse a change that leaves `member` with
    `role_after` (None for removal or leaving) when nobody else is approver."""
    after = {**role_by_member, member: role_after}
    if Role.APPROVER not in after.values():
        raise LastApproverError(
            "A project needs at least one approver. Make someone else approver first."
        )
