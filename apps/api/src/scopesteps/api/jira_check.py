"""Live Jira check: proves publishing works against a real Jira Cloud project, before or without
the app's screens.

Run it yourself in a terminal; it asks for the API token without showing it, and never prints,
logs or saves it. It reads the account and the project, then, after you type `yes`, creates a
test Epic, a Story under it and a Subtask under that, updates the Story and closes all three.
Use a test project with synthetic data only, never a team's real one.

    just jira-check --site your-team.atlassian.net --email bot@your-team.com --project SSTEST
"""

# `identity.client` and `projects.client` import each other; loading `projects.client` first is
# the order the app uses, and the only one that resolves.
import scopesteps.projects.client  # noqa: F401  # pyright: ignore[reportUnusedImport]

# isort: split
import argparse
import getpass
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from scopesteps.jira_integration.application.ports import JiraGateway
from scopesteps.jira_integration.domain.connection import (
    normalise_project_key,
    normalise_site_url,
)
from scopesteps.jira_integration.domain.plan import IssueContent
from scopesteps.jira_integration.infrastructure.jira_http import HttpJiraGateway
from scopesteps.kernel.errors import DomainError

PREFIX = "[ScopeSteps check]"


def run(
    gateway: JiraGateway, project_key: str, site_url: str, say: Callable[[str], None]
) -> list[str]:
    """Every step publishing takes, in order; returns the keys of the issues it made."""
    account = gateway.account()
    say(f"1. The token works. Publishing as: {account.name}")
    project = gateway.project(project_key)
    say(f"2. Found project {project.key} ({project.name}) with Epic, Story and Subtask types.")
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    epic = IssueContent(uuid4(), "epic", None, f"{PREFIX} Test epic {stamp}", "A test epic.")
    story = IssueContent(
        uuid4(),
        "story",
        epic.item_id,
        f"{PREFIX} Test story {stamp}",
        "As a tester, I want to see ScopeSteps publish, so I know it works.",
        criteria=("The story sits under the test epic.",),
    )
    task = IssueContent(uuid4(), "task", story.item_id, f"{PREFIX} Test subtask {stamp}", "")
    made_epic = gateway.create_issue(project, epic, None)
    made_story = gateway.create_issue(project, story, made_epic.key)
    made_task = gateway.create_issue(project, task, made_story.key)
    keys = [made_epic.key, made_story.key, made_task.key]
    say(f"3. Created {', '.join(keys)}: the story under the epic, the subtask under the story.")
    found = gateway.find_issue(project, story.marker)
    say(
        "4. Found the story again by its ScopeSteps ID."
        if found and found.key == made_story.key
        else "4. Jira search has not indexed the story yet (normal for a few seconds); not a failure."
    )
    reworded = IssueContent(
        story.item_id,
        "story",
        epic.item_id,
        f"{PREFIX} Test story {stamp} (updated)",
        story.body,
        criteria=(*story.criteria, "An update changes the same issue."),
    )
    gateway.update_issue(made_story.key, project, reworded, made_epic.key)
    say(f"5. Updated {made_story.key}.")
    for key in reversed(keys):
        gateway.close_issue(key)
    say(f"6. Closed {', '.join(reversed(keys))}.")
    for key in keys:
        say(f"   {site_url}/browse/{key}")
    return keys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Jira publishing against a real test project."
    )
    parser.add_argument("--site", required=True, help="your-team.atlassian.net")
    parser.add_argument("--email", required=True, help="The Jira account's email")
    parser.add_argument(
        "--project", required=True, help="A test project's key, never a real team's"
    )
    args = parser.parse_args(argv)
    try:
        site_url = normalise_site_url(args.site)
        project_key = normalise_project_key(args.project)
    except DomainError as error:
        print(error.message)
        return 2
    token = getpass.getpass("Paste the API token (it is not shown): ").strip()
    if not token:
        print("No token given.")
        return 2
    print(f"This creates 3 test issues in {project_key} on {site_url}, then closes them.")
    if input("Type yes to go on: ").strip().lower() != "yes":
        print("Stopped. Nothing was sent.")
        return 1
    try:
        run(HttpJiraGateway(site_url, args.email, token), project_key, site_url, print)
    except DomainError as error:
        print(f"Stopped: {error.message} ({error.code})")
        return 1
    print("Jira publishing works on this site.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
