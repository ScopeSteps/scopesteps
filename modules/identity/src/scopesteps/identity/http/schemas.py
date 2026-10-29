from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr

from scopesteps.identity.client import Role, UserId
from scopesteps.identity.domain.profile import (
    MAX_ABOUT_CHARS,
    MAX_DISPLAY_NAME_CHARS,
    MAX_JOB_TITLE_CHARS,
)
from scopesteps.identity.domain.user import MAX_EMAIL_LENGTH, MAX_PASSWORD_LENGTH
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
    revision: int = Field(
        description="Send back as expected_revision when changing the member's roles."
    )


class ProjectMembersResponse(BaseModel):
    members: list[ProjectMemberResponse]


class SignInRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    # SecretStr keeps the password out of reprs, logs and validation error details.
    password: SecretStr = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


GrantableRole = Literal["viewer", "editor", "approver"]
# Loose bounds that only stop a huge body; the exact rules are checked after normalising.
_NAME = Field(min_length=1, max_length=4 * MAX_DISPLAY_NAME_CHARS)
_PASSWORD = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class SignUpRequest(BaseModel):
    display_name: str = _NAME
    email: str = Field(min_length=1, max_length=MAX_EMAIL_LENGTH)
    password: SecretStr = _PASSWORD


class CheckYourEmailResponse(BaseModel):
    """The same for every address, so it never reveals whether one has an account."""

    message: str


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class ResendVerificationRequest(BaseModel):
    email: str = Field(min_length=1, max_length=MAX_EMAIL_LENGTH)


class InviteRequest(BaseModel):
    email: str = Field(min_length=1, max_length=MAX_EMAIL_LENGTH)
    roles: list[GrantableRole] = Field(min_length=1, max_length=3)
    send_email: bool = Field(
        default=True, description="Email the link; otherwise it is returned to copy."
    )


class InvitationResponse(BaseModel):
    id: UUID
    email: str
    roles: list[Role]
    invited_by: UserId
    invited_by_name: str
    created_at: datetime
    expires_at: datetime
    expired: bool = Field(description="Its link no longer works; make a new one to use it.")


class InvitationCreatedResponse(BaseModel):
    invitation: InvitationResponse
    link: str | None = Field(
        description="The personal link, returned once: when the email was not asked for or could "
        "not be sent. Share it privately."
    )
    email_sent: bool


class InvitationLinkResponse(BaseModel):
    invitation: InvitationResponse
    link: str = Field(description="The new link, returned once. The previous one stops working.")


class InvitationsResponse(BaseModel):
    invitations: list[InvitationResponse] = Field(description="Newest first.")


class ChangeRolesRequest(BaseModel):
    roles: list[GrantableRole] = Field(min_length=1, max_length=3)
    expected_revision: int = Field(ge=1)


class InvitationPreviewResponse(BaseModel):
    """What the person who opens an invitation link sees."""

    project_id: UUID
    project_name: str
    invited_by_name: str
    email: str
    roles: list[Role]
    expires_at: datetime
    has_account: bool = Field(
        description="Whether the invited email has an account: sign in and join, or create one."
    )


class InvitedSignUpRequest(BaseModel):
    display_name: str = _NAME
    password: SecretStr = _PASSWORD


class JoinedResponse(BaseModel):
    project_id: UUID
    user: CurrentUserResponse
