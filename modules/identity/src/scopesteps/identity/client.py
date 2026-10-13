from dataclasses import dataclass
from enum import StrEnum
from typing import NewType
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


def get_project_access() -> ProjectAccess:
    """FastAPI dependency for project-scoped routes in any module.

    Identity owns the implementation; the composition root binds it with
    `app.dependency_overrides`, so modules never import identity's internals.
    """
    raise RuntimeError("get_project_access is not bound to identity's resolver")
