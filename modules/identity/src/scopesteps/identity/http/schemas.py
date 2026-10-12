from pydantic import BaseModel

from scopesteps.identity.client import Role, UserId
from scopesteps.projects.client import ProjectId


class MembershipResponse(BaseModel):
    project_id: ProjectId
    role: Role


class CurrentUserResponse(BaseModel):
    id: UserId
    email: str
    display_name: str
    memberships: list[MembershipResponse]
