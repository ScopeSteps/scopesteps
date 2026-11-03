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


class NotificationResponse(BaseModel):
    id: NotificationId
    kind: Literal["mentioned", "replied"]
    project_id: ProjectId
    project_name: str
    item: NotificationItemResponse | None = Field(description="Null for General discussion.")
    thread_id: UUID
    comment_id: UUID
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
