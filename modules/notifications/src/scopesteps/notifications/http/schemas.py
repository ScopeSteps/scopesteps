from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from scopesteps.identity.client import UserId
from scopesteps.notifications.client import NotificationId
from scopesteps.projects.client import ProjectId


class NotificationItemResponse(BaseModel):
    id: UUID
    kind: Literal["epic", "story"]
    title: str


class NotificationDetails(BaseModel):
    """Counts only, never names or text. A publish has every count but `days_left`; a token
    notice has `days_left` (expiring) or nothing (stopped)."""

    created: int | None = None
    updated: int | None = None
    closed: int | None = None
    failed: int | None = None
    sent: int | None = None
    total: int | None = None
    days_left: int | None = None


class NotificationResponse(BaseModel):
    id: NotificationId
    kind: Literal[
        "mentioned",
        "replied",
        "jira_published",
        "jira_publish_failed",
        "jira_token_expiring",
        "jira_token_stopped",
    ] = Field(
        description="jira_published and jira_publish_failed go to whoever started the publish "
        "(the approver, for an automatic one); the token kinds go to the project's approvers."
    )
    project_id: ProjectId
    project_name: str
    item: NotificationItemResponse | None = Field(description="Null for General discussion.")
    thread_id: UUID | None = Field(description="Set for mentioned and replied only.")
    comment_id: UUID | None = Field(description="Set for mentioned and replied only.")
    subject_id: UUID | None = Field(
        description="For a Jira kind: the publish, or the token state it is about."
    )
    version_id: UUID | None = Field(description="The approved version a publish sent.")
    details: NotificationDetails | None = Field(description="For a Jira kind only.")
    actor_id: UserId
    actor_name: str = Field(description="As it is now.")
    created_at: datetime
    read_at: datetime | None


class NotificationPageResponse(BaseModel):
    notifications: list[NotificationResponse] = Field(description="Newest first.")
    next_cursor: str | None = Field(
        description="Send as `cursor` to read the next, older page. Null on the last page."
    )


class UnreadCountResponse(BaseModel):
    unread: int


class NotificationSettings(BaseModel):
    email_on_mention: bool = Field(description="Email when someone mentions me. On by default.")
    email_on_reply: bool = Field(
        description="Email about replies to threads I follow. Off by default."
    )
    email_on_jira_failure: bool = Field(
        description="Email when a Jira publish I started fails. On by default."
    )


class NotificationSettingsRequest(BaseModel):
    email_on_mention: bool
    email_on_reply: bool
    email_on_jira_failure: bool | None = Field(
        default=None, description="Left out, it keeps its saved value."
    )
