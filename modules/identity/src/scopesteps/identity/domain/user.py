from dataclasses import dataclass
from datetime import datetime

from scopesteps.identity.client import Role, UserId
from scopesteps.projects.client import ProjectId


@dataclass(frozen=True)
class User:
    id: UserId
    email: str
    display_name: str
    created_at: datetime


@dataclass(frozen=True)
class Membership:
    """A project-scoped role. Roles combine; none implies another."""

    user_id: UserId
    project_id: ProjectId
    role: Role
    granted_at: datetime
