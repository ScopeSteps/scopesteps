from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr

from scopesteps.backlog.client import BacklogVersionId
from scopesteps.identity.client import UserId
from scopesteps.jira_integration.domain.ids import PublishId


class ConnectRequest(BaseModel):
    site_url: str = Field(
        min_length=1, max_length=255, description="The Jira Cloud address: your-team.atlassian.net."
    )
    email: str = Field(min_length=3, max_length=254, description="The Jira account's email.")
    api_token: SecretStr = Field(
        min_length=1,
        max_length=512,
        description="An API token of that account. Stored encrypted and never returned.",
    )
    project_key: str = Field(min_length=2, max_length=10, description="The Jira project, e.g. WEB.")


Publishers = Literal["approvers", "approvers_and_editors"]


class SettingsRequest(BaseModel):
    """Fields left out are unchanged."""

    auto_publish: bool | None = Field(
        default=None,
        description="Publish every newly approved version to Jira without asking. Off by default.",
    )
    publishers: Publishers | None = Field(
        default=None,
        description="Who may preview and publish: approvers only (the default), or editors too. "
        "Connecting Jira and these settings stay with approvers.",
    )
    expected_revision: int = Field(ge=1)


class ConnectionResponse(BaseModel):
    """A project's Jira connection. The API token is never part of it."""

    site_url: str
    email: str | None = Field(description="The Jira account's email; shown to approvers only.")
    jira_project_key: str
    jira_project_name: str
    auto_publish: bool
    publishers: Publishers
    connected_by: UserId
    connected_at: datetime
    checked_at: datetime = Field(description="When the details last worked.")
    revision: int = Field(description="Send back as expected_revision when changing settings.")


class ConnectionStatusResponse(BaseModel):
    configured: bool = Field(
        description="False when the server has no JIRA_TOKEN_KEY, so Jira cannot be connected."
    )
    connection: ConnectionResponse | None
    can_publish: bool = Field(description="Whether you may preview and publish in this project.")
    can_manage: bool = Field(description="Whether you may connect Jira and change its settings.")


IssueKind = Literal["epic", "story", "task"]


class KindCounts(BaseModel):
    kind: IssueKind
    create: int
    update: int
    close: int
    unchanged: int


class PreviewResponse(BaseModel):
    """What publishing the version would do now. Nothing has been sent to Jira."""

    version_id: BacklogVersionId
    jira_project_key: str
    counts: list[KindCounts] = Field(description="Epics, stories and tasks (Jira Sub-tasks).")


class PublishRequest(BaseModel):
    version_id: BacklogVersionId


class FailedItem(BaseModel):
    item_id: UUID = Field(description="The epic, story or task that did not reach Jira.")
    kind: IssueKind
    operation: Literal["create", "update", "close"]
    error_code: str


class PublishResponse(BaseModel):
    id: PublishId
    version_id: BacklogVersionId
    status: Literal["sending", "done", "failed"] = Field(
        description="sending: the server is sending it, with no page needed. failed: some items "
        "did not reach Jira; retry sends only those."
    )
    created_by: UserId
    created_at: datetime
    finished_at: datetime | None
    last_error: str | None = Field(
        description="Why the last advance stopped early: JIRA_RATE_LIMITED or JIRA_UNAVAILABLE "
        "(advance again later), or the code that failed the whole publish."
    )
    next_attempt_at: datetime | None = Field(
        description="When the background sender tries again, after a rate limit or an "
        "unreachable Jira."
    )
    total: int = Field(description="Operations planned.")
    sent: int
    counts: list[KindCounts] = Field(description="What the publish does, by kind.")
    failed: list[FailedItem]
    revision: int


class PublishListResponse(BaseModel):
    publishes: list[PublishResponse] = Field(description="The 20 newest first.")


class IssueLinkResponse(BaseModel):
    item_id: UUID
    kind: IssueKind
    jira_key: str
    url: str | None = Field(description="Null when the project is no longer connected.")
    closed: bool = Field(description="Closed because the item left the backlog.")


class IssueLinkListResponse(BaseModel):
    issues: list[IssueLinkResponse]
