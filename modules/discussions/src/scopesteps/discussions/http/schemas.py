from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from scopesteps.backlog.client import BacklogVersionId, ItemId
from scopesteps.discussions.client import CommentId, ThreadId
from scopesteps.discussions.domain.thread import MAX_BODY_CHARS
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId

# Room for surrounding whitespace, which is trimmed before the limit is checked.
_RAW_BODY_CHARS = MAX_BODY_CHARS * 2


class StartThreadRequest(BaseModel):
    item_id: ItemId | None = Field(
        default=None,
        description="An epic or story in the current backlog; null or absent starts a thread in "
        "General discussion.",
    )
    body: str = Field(
        max_length=_RAW_BODY_CHARS,
        description=f"Plain text, trimmed, 1 to {MAX_BODY_CHARS:,} characters.",
    )


class ReplyRequest(BaseModel):
    body: str = Field(max_length=_RAW_BODY_CHARS)


class EditCommentRequest(BaseModel):
    body: str = Field(max_length=_RAW_BODY_CHARS)
    expected_revision: int


class ThreadStateRequest(BaseModel):
    expected_revision: int


class CommentResponse(BaseModel):
    id: CommentId
    author_id: UserId
    author_name: str = Field(description="As it was when the comment was written.")
    body: str | None = Field(
        description="Plain text exactly as written; render it escaped. Null once deleted."
    )
    deleted: bool = Field(
        description="Shown as a placeholder only while replies follow it; otherwise left out."
    )
    revision: int = Field(description="Send back as expected_revision when editing.")
    backlog_version_id: BacklogVersionId | None = Field(
        description="The backlog version in flight, or else the baseline, when it was written."
    )
    created_at: datetime
    edited_at: datetime | None


class ThreadItemResponse(BaseModel):
    id: ItemId
    kind: Literal["epic", "story"]
    title: str
    in_current_backlog: bool = Field(
        description="False once the item is no longer in the backlog; the thread stays readable."
    )


class ThreadResponse(BaseModel):
    id: ThreadId
    project_id: ProjectId
    item_id: ItemId | None = Field(description="Null for General discussion.")
    item: ThreadItemResponse | None
    status: Literal["open", "resolved"]
    revision: int = Field(description="Send back as expected_revision to resolve or reopen.")
    created_by: UserId
    created_at: datetime
    last_activity_at: datetime
    resolved_at: datetime | None
    resolved_by: UserId | None
    resolved_by_name: str | None
    comments: list[CommentResponse] = Field(
        description="Oldest first: the first comment, then replies."
    )


class ThreadPageResponse(BaseModel):
    threads: list[ThreadResponse] = Field(description="Newest activity first.")
    next_cursor: str | None = Field(
        description="Send as `cursor` to read the next, older page. Null on the last page."
    )


class ItemThreadCount(BaseModel):
    item_id: UUID
    open_threads: int


class ThreadCountsResponse(BaseModel):
    items: list[ItemThreadCount] = Field(description="Only items with an open thread.")
    general_open_threads: int
