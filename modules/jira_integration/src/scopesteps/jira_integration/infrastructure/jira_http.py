"""Jira Cloud's REST API v3 over HTTPS, with basic auth from an account email and API token.

Every failure becomes a `domain.errors` class with a plain message. Messages and details never
carry the token, the request body or Jira's own error text, which can echo what was sent.
"""

from collections.abc import Callable
from http import HTTPStatus
from typing import Any, cast

import httpx

from scopesteps.jira_integration.application.ports import JiraIssue
from scopesteps.jira_integration.domain.connection import IssueTypes, JiraAccount, JiraProject
from scopesteps.jira_integration.domain.errors import (
    JiraAuthFailedError,
    JiraForbiddenError,
    JiraNoDoneStatusError,
    JiraProjectNotFoundError,
    JiraProjectUnsuitableError,
    JiraRateLimitedError,
    JiraRejectedError,
    JiraUnavailableError,
)
from scopesteps.jira_integration.domain.plan import IssueContent

TIMEOUT_SECONDS = 20.0
Json = dict[str, Any]


class HttpJiraGateway:
    def __init__(
        self,
        site_url: str,
        email: str,
        api_token: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=f"{site_url}/rest/api/3",
            auth=httpx.BasicAuth(email, api_token),
            timeout=TIMEOUT_SECONDS,
            transport=transport,
            headers={"Accept": "application/json"},
            follow_redirects=False,
        )

    def account(self) -> JiraAccount:
        me = self._request("GET", "/myself")
        return JiraAccount(
            id=str(me.get("accountId", "")), name=str(me.get("displayName", "Jira account"))
        )

    def project(self, key: str) -> JiraProject:
        found = self._request("GET", f"/project/{key}", not_found=JiraProjectNotFoundError)
        types = self._request("GET", f"/issue/createmeta/{key}/issuetypes")
        listed = cast(list[Json], types.get("issueTypes") or types.get("values") or [])
        return JiraProject(
            id=str(found["id"]),
            key=str(found["key"]),
            name=str(found.get("name", key)),
            issue_types=_issue_types(listed),
        )

    def create_issue(
        self, project: JiraProject, issue: IssueContent, parent_key: str | None
    ) -> JiraIssue:
        fields = _fields(project, issue, parent_key)
        fields["project"] = {"id": project.id}
        fields["issuetype"] = {"id": _type_of(project, issue)}
        created = self._request("POST", "/issue", json={"fields": fields})
        return JiraIssue(id=str(created["id"]), key=str(created["key"]))

    def update_issue(
        self, key: str, project: JiraProject, issue: IssueContent, parent_key: str | None
    ) -> None:
        # A task is only its title in ScopeSteps, so its subtask's description belongs to the
        # team: their notes are never overwritten. Its parent is fixed in Jira (ADR 0029).
        fields = (
            {"summary": issue.summary}
            if issue.kind == "task"
            else _fields(project, issue, parent_key)
        )
        self._request("PUT", f"/issue/{key}", json={"fields": fields})

    def close_issue(self, key: str) -> None:
        current = self._request("GET", f"/issue/{key}", params={"fields": "status"})
        status = cast(Json, cast(Json, current.get("fields", {})).get("status", {}))
        if _category(status) == "done":
            return
        listed = self._request("GET", f"/issue/{key}/transitions")
        for transition in cast(list[Json], listed.get("transitions", [])):
            if _category(cast(Json, transition.get("to", {}))) == "done":
                self._request(
                    "POST",
                    f"/issue/{key}/transitions",
                    json={"transition": {"id": transition["id"]}},
                )
                return
        raise JiraNoDoneStatusError(
            f"Jira offers no way to move {key} to a done status, so it was left open."
        )

    def find_issue(self, project: JiraProject, marker: str) -> JiraIssue | None:
        jql = f'project = "{project.key}" AND text ~ "\\"{marker}\\""'
        found = self._request(
            "POST", "/search/jql", json={"jql": jql, "fields": ["summary"], "maxResults": 1}
        )
        issues = cast(list[Json], found.get("issues", []))
        if not issues:
            return None
        return JiraIssue(id=str(issues[0]["id"]), key=str(issues[0]["key"]))

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Json | None = None,
        params: dict[str, str] | None = None,
        not_found: type[Exception] = JiraRejectedError,
    ) -> Json:
        try:
            response = self._client.request(method, path, json=json, params=params)
        except httpx.HTTPError as error:
            raise JiraUnavailableError(
                "Jira could not be reached. Try again in a few minutes."
            ) from error
        status = response.status_code
        if status == HTTPStatus.UNAUTHORIZED:
            raise JiraAuthFailedError(
                "Jira did not accept the email and API token. Check them, or make a new token."
            )
        if status == HTTPStatus.FORBIDDEN:
            raise JiraForbiddenError(
                "The Jira account is not allowed to do this in the project. Check its permissions."
            )
        if status == HTTPStatus.NOT_FOUND:
            raise not_found("Jira has no such project, or the account cannot see it.")
        if status == HTTPStatus.TOO_MANY_REQUESTS:
            raise JiraRateLimitedError(
                "Jira asked to slow down. Publishing goes on in a minute.",
                details={"retry_after_seconds": _retry_after(response)},
            )
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            raise JiraUnavailableError("Jira had a problem. Try again in a few minutes.")
        if status >= HTTPStatus.BAD_REQUEST:
            raise JiraRejectedError(
                "Jira did not accept this issue.",
                details={"fields": _refused_fields(response)},
            )
        if status == HTTPStatus.NO_CONTENT or not response.content:
            return {}
        return cast(Json, response.json())


def _issue_types(listed: list[Json]) -> IssueTypes:
    def find(match: Callable[[Json], bool]) -> str | None:
        return next((str(each["id"]) for each in listed if match(each)), None)

    def level(issue_type: Json) -> object:
        return issue_type.get("hierarchyLevel")

    epic = find(lambda t: level(t) == 1) or find(lambda t: t.get("name") == "Epic")
    story = find(lambda t: t.get("name") == "Story") or find(
        lambda t: level(t) in (0, None) and t.get("subtask") is not True
    )
    subtask = find(lambda t: t.get("subtask") is True or level(t) == -1)
    if epic is None or story is None or subtask is None:
        raise JiraProjectUnsuitableError(
            "The Jira project needs Epic, Story and Sub-task issue types. Choose a Scrum or "
            "Kanban software project."
        )
    return IssueTypes(epic=epic, story=story, subtask=subtask)


def _type_of(project: JiraProject, issue: IssueContent) -> str:
    types = project.issue_types
    return {"epic": types.epic, "story": types.story, "task": types.subtask}[issue.kind]


def _fields(project: JiraProject, issue: IssueContent, parent_key: str | None) -> Json:
    fields: Json = {"summary": issue.summary, "description": description(issue)}
    if parent_key is not None:
        fields["parent"] = {"key": parent_key}
    return fields


def description(issue: IssueContent) -> Json:
    """The item in Atlassian Document Format: its text, criteria, assumptions and open questions
    as in the CSV export (ADR 0014), then a link back and the marker that finds it again."""
    content: list[Json] = [_paragraph(part) for part in issue.body.split("\n\n") if part.strip()]
    for heading, entries in (
        ("Acceptance criteria", issue.criteria),
        ("Assumptions", issue.assumptions),
        ("Open questions", issue.open_questions),
    ):
        if entries:
            content.append({"type": "heading", "attrs": {"level": 3}, "content": [_text(heading)]})
            content.append(
                {
                    "type": "bulletList",
                    "content": [
                        {"type": "listItem", "content": [_paragraph(entry)]} for entry in entries
                    ],
                }
            )
    footer: list[Json] = []
    if issue.link:
        footer.append(
            {
                "type": "text",
                "text": "Open in ScopeSteps",
                "marks": [{"type": "link", "attrs": {"href": issue.link}}],
            }
        )
        footer.append(_text(" · "))
    footer.append(_text(issue.marker))
    content.append({"type": "paragraph", "content": footer})
    return {"type": "doc", "version": 1, "content": content}


def _paragraph(text: str) -> Json:
    return {"type": "paragraph", "content": [_text(" ".join(text.split()))]}


def _text(text: str) -> Json:
    return {"type": "text", "text": text}


def _category(status: Json) -> str | None:
    category = status.get("statusCategory")
    return cast(Json, category).get("key") if isinstance(category, dict) else None


def _retry_after(response: httpx.Response) -> int:
    value = response.headers.get("Retry-After", "")
    return int(value) if value.isdigit() else 60


def _refused_fields(response: httpx.Response) -> list[str]:
    """The names of the fields Jira refused, never its messages, which can quote the values."""
    try:
        body: object = response.json()
    except ValueError:
        return []
    if not isinstance(body, dict):
        return []
    errors: object = cast(Json, body).get("errors")
    return sorted(str(name) for name in cast(Json, errors)) if isinstance(errors, dict) else []
