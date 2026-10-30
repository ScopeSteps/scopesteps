"""What waits for the actor across their projects, for the home page.

Each count is one a role held in that project lets the actor act on, read for all the actor's
projects at once so the number of reads does not grow with the list.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from scopesteps.audit.client import RecentActivity
from scopesteps.backlog.client import BacklogVersionId, ScopeState, ScopeStatus
from scopesteps.identity.client import Actor, Memberships, Role
from scopesteps.projects.application.projects import ProjectStore, StatusReader
from scopesteps.projects.domain.ids import ProjectId
from scopesteps.projects.domain.project import Project

ACTIVITY_WINDOW = timedelta(days=7)

SUMMARY_ROLES = (Role.APPROVER, Role.EDITOR, Role.VIEWER)
"""The roles the app grants, in the order the summary names them."""


class WorkCounts(Protocol):
    """Each read covers every project or version given in one go; ids with nothing to count may
    be absent. No read checks access: the use case passes only the actor's projects."""

    def change_requests_in_review(
        self, project_ids: Collection[ProjectId]
    ) -> Mapping[ProjectId, int]: ...

    def open_questions(self, project_ids: Collection[ProjectId]) -> Mapping[ProjectId, int]:
        """Clarification questions waiting for an answer in runs that wait for input."""
        ...

    def draft_blockers(
        self, version_ids: Collection[BacklogVersionId]
    ) -> Mapping[BacklogVersionId, int]:
        """Blockers of each version that is still a draft; other versions are absent."""
        ...

    def unconfirmed_speakers(self, project_ids: Collection[ProjectId]) -> Mapping[ProjectId, int]:
        """Speakers in current transcripts nobody has said who they are (ADR 0012)."""
        ...

    def recent_activity(
        self, project_ids: Collection[ProjectId], since: datetime
    ) -> Mapping[ProjectId, RecentActivity]: ...


@dataclass(frozen=True)
class ApproverWork:
    change_requests_in_review: int
    draft_ready_for_approval: bool
    """A draft is in progress and nothing blocks it."""

    @property
    def waiting(self) -> int:
        return self.change_requests_in_review + int(self.draft_ready_for_approval)


@dataclass(frozen=True)
class EditorWork:
    open_questions: int
    draft_blockers: int
    unconfirmed_speakers: int

    @property
    def waiting(self) -> int:
        return self.open_questions + self.draft_blockers + self.unconfirmed_speakers


@dataclass(frozen=True)
class ProjectWork:
    """One project as the actor's roles in it let them act on it. Recent activity is shown to
    every member but waits for nobody, so it is not part of `waiting`."""

    project: Project
    roles: frozenset[Role]
    status: ScopeStatus
    approver: ApproverWork | None
    editor: EditorWork | None
    activity: RecentActivity | None

    @property
    def waiting(self) -> int:
        return sum(work.waiting for work in (self.approver, self.editor) if work is not None)


@dataclass(frozen=True)
class RoleTotal:
    role: Role
    projects: int
    waiting: int


@dataclass(frozen=True)
class MyWork:
    projects: tuple[ProjectWork, ...]
    """Most waiting first, then by name."""
    roles: tuple[RoleTotal, ...]
    """One per role in `SUMMARY_ROLES`, including those the actor holds nowhere."""


def my_work(
    projects: ProjectStore,
    memberships: Memberships,
    statuses_of: StatusReader,
    counts: WorkCounts,
    actor: Actor,
    now: datetime,
) -> MyWork:
    roles = {m.project_id: m.roles for m in memberships.of_user(actor.user_id)}
    found = projects.get_many(roles.keys()) if roles else []
    ids = [project.id for project in found]
    if not ids:
        return MyWork((), tuple(RoleTotal(role, 0, 0) for role in SUMMARY_ROLES))

    def holding(role: Role) -> list[ProjectId]:
        return [project_id for project_id in ids if role in roles[project_id]]

    approving, editing = holding(Role.APPROVER), holding(Role.EDITOR)
    statuses = statuses_of(ids)
    drafts = {
        project_id: version_id
        for project_id in {*approving, *editing}
        if statuses[project_id].state is ScopeState.DRAFT_IN_PROGRESS
        and (version_id := statuses[project_id].open_version_id) is not None
    }
    # A role held nowhere asks nothing, so nobody is counted for a role they do not hold.
    blockers: Mapping[BacklogVersionId, int] = (
        counts.draft_blockers(drafts.values()) if drafts else {}
    )
    in_review: Mapping[ProjectId, int] = (
        counts.change_requests_in_review(approving) if approving else {}
    )
    questions: Mapping[ProjectId, int] = counts.open_questions(editing) if editing else {}
    speakers: Mapping[ProjectId, int] = counts.unconfirmed_speakers(editing) if editing else {}
    activity = counts.recent_activity(ids, now - ACTIVITY_WINDOW)

    def draft_blockers(project_id: ProjectId) -> int | None:
        version_id = drafts.get(project_id)
        return None if version_id is None else blockers.get(version_id)

    views = [
        ProjectWork(
            project=project,
            roles=roles[project.id],
            status=statuses[project.id],
            approver=ApproverWork(
                change_requests_in_review=in_review.get(project.id, 0),
                draft_ready_for_approval=draft_blockers(project.id) == 0,
            )
            if project.id in approving
            else None,
            editor=EditorWork(
                open_questions=questions.get(project.id, 0),
                draft_blockers=draft_blockers(project.id) or 0,
                unconfirmed_speakers=speakers.get(project.id, 0),
            )
            if project.id in editing
            else None,
            activity=activity.get(project.id),
        )
        for project in found
    ]
    views.sort(key=lambda view: (-view.waiting, view.project.name.casefold(), view.project.id))
    return MyWork(tuple(views), tuple(_total(role, views) for role in SUMMARY_ROLES))


def _total(role: Role, views: Collection[ProjectWork]) -> RoleTotal:
    held = [view for view in views if role in view.roles]
    work = {Role.APPROVER: _approver_waiting, Role.EDITOR: _editor_waiting}.get(role)
    return RoleTotal(role, len(held), sum(work(view) for view in held) if work else 0)


def _approver_waiting(view: ProjectWork) -> int:
    return 0 if view.approver is None else view.approver.waiting


def _editor_waiting(view: ProjectWork) -> int:
    return 0 if view.editor is None else view.editor.waiting
