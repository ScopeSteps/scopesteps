"""Invitations to a project and the rules about who holds which role in it (ADR 0019)."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import NewType
from uuid import UUID

from scopesteps.identity.client import Role, UserId
from scopesteps.identity.domain.errors import LastApproverError, RolesInvalidError
from scopesteps.projects.client import ProjectId

InvitationId = NewType("InvitationId", UUID)

GRANTABLE_ROLES = frozenset({Role.VIEWER, Role.EDITOR, Role.APPROVER})
"""The project roles an approver may give. The workspace and integration admin roles are not
granted per project from the app."""


def grantable_roles(roles: Collection[Role]) -> frozenset[Role]:
    chosen = frozenset(roles)
    if not chosen:
        raise RolesInvalidError("Choose at least one role")
    if not chosen <= GRANTABLE_ROLES:
        raise RolesInvalidError("Only the viewer, editor and approver roles can be given")
    return chosen


@dataclass(frozen=True)
class Invitation:
    """A personal invitation for one email address to join one project with some roles. Only the
    hash of its link's token is kept; making a new link replaces it."""

    id: InvitationId
    project_id: ProjectId
    email: str
    roles: frozenset[Role]
    invited_by: UserId
    token_hash: str
    expires_at: datetime
    created_at: datetime
    accepted_at: datetime | None = None

    def is_open(self, now: datetime) -> bool:
        """Its link still works: not accepted and not expired. A cancelled one no longer exists."""
        return self.accepted_at is None and now < self.expires_at


def check_keeps_an_approver(
    roles_by_member: Mapping[UserId, frozenset[Role]],
    member: UserId,
    roles_after: frozenset[Role],
) -> None:
    """A project always keeps at least one approver: refuse a change that leaves `member` with
    `roles_after` (empty for removal or leaving) when nobody else is approver."""
    after = {**roles_by_member, member: roles_after}
    if not any(Role.APPROVER in roles for roles in after.values()):
        raise LastApproverError(
            "A project needs at least one approver. Make someone else approver first."
        )
