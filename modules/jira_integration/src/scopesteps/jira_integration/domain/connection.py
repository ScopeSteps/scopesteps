import re
from dataclasses import dataclass
from datetime import datetime
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

    def issue_url(self, key: str) -> str:
        return f"{self.site_url}/browse/{key}"


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
