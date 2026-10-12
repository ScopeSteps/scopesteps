from dataclasses import dataclass
from enum import StrEnum
from typing import NewType
from uuid import UUID

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
