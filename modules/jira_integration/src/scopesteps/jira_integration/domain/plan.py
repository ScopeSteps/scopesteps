"""What publishing a version does in Jira, worked out from the version and what earlier publishes
created. Pure: the same version and links always give the same plan (ADR 0029)."""

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Literal
from uuid import UUID

IssueKind = Literal["epic", "story", "task"]
Operation = Literal["create", "update", "close"]

ISSUE_KINDS: tuple[IssueKind, ...] = ("epic", "story", "task")
_CLOSE_ORDER: dict[IssueKind, int] = {"task": 0, "story": 1, "epic": 2}


@dataclass(frozen=True)
class IssueContent:
    """One epic, story or task as its Jira issue shows it."""

    item_id: UUID
    kind: IssueKind
    parent_item_id: UUID | None
    summary: str
    body: str
    criteria: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    link: str = ""
    """Back to the item's project in ScopeSteps."""

    @property
    def marker(self) -> str:
        """Written into the description, so an issue whose creation went unconfirmed is found."""
        return f"ScopeSteps ID: {self.item_id}"

    def fingerprint(self) -> str:
        """Changes exactly when what Jira shows for the item would change."""
        encoded = json.dumps(asdict(self), sort_keys=True, default=str).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class IssueLink:
    """A ScopeSteps item and the Jira issue an earlier publish made for it."""

    item_id: UUID
    kind: IssueKind
    jira_key: str
    jira_id: str
    fingerprint: str
    closed: bool = False


@dataclass(frozen=True)
class PlannedOperation:
    item_id: UUID
    kind: IssueKind
    operation: Operation
    content: IssueContent | None
    """What to send; None for a close."""
    jira_key: str | None
    """The issue to update or close; None for a create."""


@dataclass(frozen=True)
class Counts:
    create: int = 0
    update: int = 0
    close: int = 0
    unchanged: int = 0


@dataclass(frozen=True)
class Plan:
    operations: tuple[PlannedOperation, ...]
    unchanged: Mapping[IssueKind, int]

    def counts(self) -> dict[IssueKind, Counts]:
        totals: dict[IssueKind, Counts] = {}
        for kind in ISSUE_KINDS:
            ops = [op.operation for op in self.operations if op.kind == kind]
            totals[kind] = Counts(
                create=ops.count("create"),
                update=ops.count("update"),
                close=ops.count("close"),
                unchanged=self.unchanged.get(kind, 0),
            )
        return totals


@dataclass(frozen=True)
class ApprovedItem:
    """An approved epic or story, with its tasks, as `backlog` froze it."""

    id: UUID
    kind: Literal["epic", "story"]
    parent_id: UUID | None
    title: str
    description: str
    criteria: tuple[str, ...]
    assumptions: tuple[str, ...]
    open_questions: tuple[str, ...]
    tasks: tuple[tuple[UUID, str], ...]
    """Each task's id and title, in order."""


def issues_of(
    items: Sequence[ApprovedItem], summary: Callable[[str], str], link: str
) -> list[IssueContent]:
    """Every epic, then every story, then every task, so a parent always comes first. A story
    whose epic is not in the version has no parent, as in the CSV export (ADR 0014)."""
    epic_ids = {item.id for item in items if item.kind == "epic"}
    epics = [
        IssueContent(
            item.id,
            "epic",
            None,
            summary(item.title),
            item.description,
            item.criteria,
            item.assumptions,
            item.open_questions,
            link,
        )
        for item in items
        if item.kind == "epic"
    ]
    stories = [item for item in items if item.kind == "story"]
    story_issues = [
        IssueContent(
            item.id,
            "story",
            item.parent_id if item.parent_id in epic_ids else None,
            summary(item.title),
            item.description,
            item.criteria,
            item.assumptions,
            item.open_questions,
            link,
        )
        for item in stories
    ]
    tasks = [
        IssueContent(task_id, "task", story.id, summary(title), "", link=link)
        for story in stories
        for task_id, title in story.tasks
    ]
    return [*epics, *story_issues, *tasks]


def plan_publish(issues: Sequence[IssueContent], links: Mapping[UUID, IssueLink]) -> Plan:
    """Create what has no issue yet, update what changed (or was closed and is back), and close
    the open issues of items the version no longer has. Nothing is ever deleted."""
    operations: list[PlannedOperation] = []
    unchanged: dict[IssueKind, int] = {}
    present = {issue.item_id for issue in issues}
    for issue in issues:
        link = links.get(issue.item_id)
        if link is None:
            operations.append(PlannedOperation(issue.item_id, issue.kind, "create", issue, None))
        elif link.closed or link.fingerprint != issue.fingerprint():
            operations.append(
                PlannedOperation(issue.item_id, issue.kind, "update", issue, link.jira_key)
            )
        else:
            unchanged[issue.kind] = unchanged.get(issue.kind, 0) + 1
    gone = sorted(
        (link for link in links.values() if link.item_id not in present and not link.closed),
        key=lambda link: (_CLOSE_ORDER[link.kind], link.jira_key),
    )
    operations += [
        PlannedOperation(link.item_id, link.kind, "close", None, link.jira_key) for link in gone
    ]
    return Plan(tuple(operations), unchanged)
