import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from scopesteps.identity.client import UserId
from scopesteps.jira_integration.domain.errors import JiraSiteInvalidError
from scopesteps.kernel.errors import InvalidInputError
from scopesteps.projects.client import ProjectId

# Jira Cloud sites only (ADR 0029): the server calls the address a user typed, so anything
# else would let a project point it at internal hosts.
_CLOUD_HOSTS = (".atlassian.net", ".jira.com")
_PROJECT_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,9}$")


Publishers = Literal["approvers", "approvers_and_editors"]
"""Who may publish to Jira in a project. Connecting and its settings stay with approvers."""


@dataclass(frozen=True)
class IssueTypes:
    """The ids of the Jira project's issue types each kind of item becomes."""

    epic: str
    story: str
    subtask: str


@dataclass(frozen=True)
class JiraProject:
    id: str
    key: str
    name: str
    issue_types: IssueTypes


TokenState = Literal["working", "expires_soon", "expired", "rejected"]

EXPIRY_WARNING = timedelta(days=14)
"""How long before its expiry date a token shows as expiring soon."""
LONGEST_TOKEN = timedelta(days=400)
"""Atlassian API tokens last at most a year; a little room for time zones and typing."""


@dataclass(frozen=True)
class JiraAccount:
    """The Jira account the token belongs to, as Jira names it (ADR 0029: a dedicated one is
    recommended, so publishing never depends on one person's account)."""

    id: str
    name: str


@dataclass(frozen=True)
class JiraConnection:
    """One project's Jira Cloud connection. The API token is held only as ciphertext."""

    project_id: ProjectId
    site_url: str
    email: str
    token_ciphertext: bytes
    jira_project: JiraProject
    auto_publish: bool
    revision: int
    connected_by: UserId
    connected_at: datetime
    checked_at: datetime
    publishers: Publishers = "approvers"
    account: JiraAccount = JiraAccount(id="", name="")
    token_expires_on: date | None = None
    """When the API token expires, as the approver entered it; None when not given."""
    token_rejected_at: datetime | None = None
    """When Jira last refused the token; cleared by a test or connection that works."""

    def issue_url(self, key: str) -> str:
        return f"{self.site_url}/browse/{key}"

    def token_state(self, today: date) -> TokenState:
        if self.token_rejected_at is not None:
            return "rejected"
        if self.token_expires_on is None:
            return "working"
        if today >= self.token_expires_on:
            return "expired"
        if self.token_expires_on - today <= EXPIRY_WARNING:
            return "expires_soon"
        return "working"

    def token_days_left(self, today: date) -> int | None:
        if self.token_expires_on is None:
            return None
        return max((self.token_expires_on - today).days, 0)

    def rejected(self, now: datetime) -> JiraConnection:
        return replace(self, token_rejected_at=now)


def check_token_expiry(expires_on: date | None, today: date) -> date | None:
    """The expiry date an approver typed: today or later, and within a token's longest life."""
    if expires_on is None:
        return None
    if expires_on <= today:
        raise InvalidInputError(
            "That expiry date has passed. Make a new API token and enter its expiry date."
        )
    if expires_on - today > LONGEST_TOKEN:
        raise InvalidInputError(
            "Jira API tokens last at most a year. Check the expiry date shown when you made it."
        )
    return expires_on


def normalise_site_url(raw: str) -> str:
    """`https://team.atlassian.net`, from what a user typed or pasted (a path is dropped)."""
    text = raw.strip()
    if "://" not in text:
        text = f"https://{text}"
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or parts.port is not None
        or parts.username is not None
        or not any(host.endswith(suffix) and len(host) > len(suffix) for suffix in _CLOUD_HOSTS)
    ):
        raise JiraSiteInvalidError(
            "Enter your Jira Cloud address, like https://your-team.atlassian.net."
        )
    return f"https://{host}"


def normalise_project_key(raw: str) -> str:
    key = raw.strip().upper()
    if not _PROJECT_KEY.match(key):
        raise InvalidInputError(
            "Enter the Jira project key: 2 to 10 letters or digits, starting with a letter, like WEB."
        )
    return key
