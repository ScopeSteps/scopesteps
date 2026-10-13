from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from scopesteps.audit.domain.event import ActorKind, EventType, SubjectKind
from scopesteps.audit.domain.ids import AuditEventId
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId


class ActivityActor(BaseModel):
    kind: ActorKind
    user_id: UserId | None = Field(description="Null when the agent acted.")
    display_name: str | None = Field(
        description="The user's name when they acted. Null when the agent acted."
    )


class ActivitySubject(BaseModel):
    kind: SubjectKind
    id: UUID


class ActivityEvent(BaseModel):
    id: AuditEventId
    project_id: ProjectId
    type: EventType
    actor: ActivityActor
    subjects: list[ActivitySubject] = Field(description="What the event concerns, by id.")
    summary: str
    occurred_at: datetime


class ActivityFeedResponse(BaseModel):
    events: list[ActivityEvent]
    next_cursor: str | None = Field(
        description="Send as `cursor` to read the next, older page. Null on the last page."
    )
