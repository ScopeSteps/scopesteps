from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from scopesteps.backlog.client import BacklogVersionId, ItemId
from scopesteps.change_control.client import ChangeRequestId, ChangeRequestStatus
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
        description=f"Plain text, trimmed, 1 to {MAX_BODY_CHARS:,} characters. A mention is "
        "written <@user_id>; a person who is not a current member is 422 `MENTION_NOT_MEMBER`.",
    )


class ReplyRequest(BaseModel):
    body: str = Field(max_length=_RAW_BODY_CHARS)


class EditCommentRequest(BaseModel):
    body: str = Field(max_length=_RAW_BODY_CHARS)
    expected_revision: int


class ThreadStateRequest(BaseModel):
    expected_revision: int


class FollowRequest(BaseModel):
    following: bool


class MentionResponse(BaseModel):
    user_id: UserId
    display_name: str = Field(description="As it is now, so a renamed person reads correctly.")


class ParticipantResponse(BaseModel):
    user_id: UserId
    display_name: str = Field(description="As it is now, so a renamed person reads correctly.")
    wrote: bool = Field(description="Wrote a comment that is not deleted.")
    mentioned: bool = Field(description="Named in a comment that is not deleted.")
    following: bool = Field(description="Gets notified of replies.")
    left_project: bool = Field(
        description='No longer a member: show them as "left the project"; they cannot follow.'
    )


class LinkedChangeRequestResponse(BaseModel):
    id: ChangeRequestId
    number: int = Field(description="Shown as CR-1, CR-2, ...")
    status: ChangeRequestStatus


class ChangeRequestDraftResponse(BaseModel):
    text: str = Field(
        description="The thread quoted one paragraph per comment, for the person to edit."
    )
    shortened: bool = Field(description="True when older comments were left out to fit.")


class CommentResponse(BaseModel):
    id: CommentId
    author_id: UserId
    author_name: str = Field(description="As it was when the comment was written.")
    body: str | None = Field(
        description="Plain text exactly as written, mentions as <@user_id>; render it escaped. "
        "Null once deleted."
    )
    mentions: list[MentionResponse] = Field(description="Who the body's <@user_id> tokens name.")
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
    following: bool = Field(description="Whether you follow the thread.")
    participants: list[ParticipantResponse] = Field(
        description="Everyone who wrote, is mentioned or follows, in the order they first appear "
        "in the comments, then other followers by name. People who left are included."
    )
    change_requests: list[LinkedChangeRequestResponse] = Field(
        description="What the thread was sent as, oldest first."
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
