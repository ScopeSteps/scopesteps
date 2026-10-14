from pydantic import BaseModel, Field, SecretStr

from scopesteps.identity.client import Role, UserId
from scopesteps.identity.domain.profile import (
    MAX_ABOUT_CHARS,
    MAX_DISPLAY_NAME_CHARS,
    MAX_JOB_TITLE_CHARS,
)
from scopesteps.identity.domain.user import MAX_PASSWORD_LENGTH
from scopesteps.projects.client import ProjectId


class MembershipResponse(BaseModel):
    project_id: ProjectId
    role: Role


class CurrentUserResponse(BaseModel):
    id: UserId
    email: str
    display_name: str
    job_title: str
    about: str
    revision: int = Field(description="Send back as expected_revision when updating the profile.")
    memberships: list[MembershipResponse]


class UpdateProfileRequest(BaseModel):
    # Loose bounds that only stop a huge body; the exact limits are checked after normalising
    # and reported as 422 PROFILE_INVALID with the field.
    display_name: str = Field(max_length=4 * MAX_DISPLAY_NAME_CHARS)
    job_title: str = Field(default="", max_length=4 * MAX_JOB_TITLE_CHARS)
    about: str = Field(default="", max_length=4 * MAX_ABOUT_CHARS)
    expected_revision: int = Field(
        ge=1, description="The revision the caller last read. A stale one returns 409."
    )


class ProjectMemberResponse(BaseModel):
    user_id: UserId
    display_name: str
    job_title: str
    roles: list[Role]


class ProjectMembersResponse(BaseModel):
    members: list[ProjectMemberResponse]


class SignInRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    # SecretStr keeps the password out of reprs, logs and validation error details.
    password: SecretStr = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
