from pydantic import BaseModel, Field, SecretStr

from scopesteps.identity.client import Role, UserId
from scopesteps.identity.domain.user import MAX_PASSWORD_LENGTH
from scopesteps.projects.client import ProjectId


class MembershipResponse(BaseModel):
    project_id: ProjectId
    role: Role


class CurrentUserResponse(BaseModel):
    id: UserId
    email: str
    display_name: str
    memberships: list[MembershipResponse]


class SignInRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    # SecretStr keeps the password out of reprs, logs and validation error details.
    password: SecretStr = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
