import hashlib
import json
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from scopesteps.backlog.client import ScopeStatus
from scopesteps.identity.client import Actor, Memberships, ProjectAccess, Role, UserId
from scopesteps.kernel.errors import ConflictError, NotFoundError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.domain.ids import ProjectId
from scopesteps.projects.domain.project import Project, ProjectChangedError, normalize_name

# Roles combine and none implies another: Editor adds sources and renames, Approver approves
# scope. Whoever starts a project has to be able to do both.
CREATOR_ROLES = (Role.EDITOR, Role.APPROVER)


class IdempotencyKeyReusedError(ConflictError):
    code = "IDEMPOTENCY_KEY_REUSED"


@dataclass(frozen=True)
class Receipt:
    """An accepted command, kept so a retry with the same Idempotency-Key does not act twice."""

    actor_id: UserId
    idempotency_key: str
    project_id: ProjectId
    fingerprint: str
    created_at: datetime


@dataclass(frozen=True)
class ProjectView:
    """A project as one member sees it."""

    project: Project
    roles: frozenset[Role]
    status: ScopeStatus


@dataclass(frozen=True)
class CreateProject:
    idempotency_key: str
    name: str


@dataclass(frozen=True)
class RenameProject:
    idempotency_key: str
    name: str
    expected_revision: int


class ProjectStore(Protocol):
    def get(self, project_id: ProjectId) -> Project | None: ...

    def get_many(self, project_ids: Collection[ProjectId]) -> list[Project]: ...

    def add(self, project: Project) -> None:
        """Insert within the caller's transaction; the caller commits."""
        ...

    def rename(self, project_id: ProjectId, name: str, *, expected_revision: int) -> bool:
        """Set the name and move to the next revision. False, changing nothing, if the stored
        revision is not `expected_revision`."""
        ...


class ReceiptStore(Protocol):
    def find(self, actor_id: UserId, idempotency_key: str) -> Receipt | None: ...

    def add(self, receipt: Receipt) -> None: ...


StatusReader = Callable[[Collection[ProjectId]], Mapping[ProjectId, ScopeStatus]]
"""A status for every id given, read in one go."""


def list_projects(
    projects: ProjectStore, memberships: Memberships, statuses_of: StatusReader, actor: Actor
) -> list[ProjectView]:
    """The actor's projects by name. The number of reads does not grow with the list."""
    roles = {
        membership.project_id: membership.roles for membership in memberships.of_user(actor.user_id)
    }
    if not roles:
        return []
    found = projects.get_many(roles.keys())
    statuses = statuses_of([project.id for project in found])
    return [
        ProjectView(project, roles[project.id], statuses[project.id])
        for project in sorted(found, key=lambda p: (p.name.casefold(), p.id))
    ]


def get_project(
    projects: ProjectStore, statuses_of: StatusReader, access: ProjectAccess
) -> ProjectView:
    access.require_member()
    return _view(projects, statuses_of, access.project_id, access.roles)


def create_project(
    projects: ProjectStore,
    receipts: ReceiptStore,
    memberships: Memberships,
    statuses_of: StatusReader,
    actor: Actor,
    command: CreateProject,
    now: datetime,
) -> ProjectView:
    """Create the project and make the actor its editor and approver, together or not at all."""
    name = normalize_name(command.name)
    fingerprint = _fingerprint("create", None, name)
    replayed = _replayed_project(receipts, actor, command.idempotency_key, fingerprint)
    if replayed is not None:
        held = memberships.of_user(actor.user_id)
        roles = next((m.roles for m in held if m.project_id == replayed), None)
        if roles is None:
            raise NotFoundError("Project not found")
        return _view(projects, statuses_of, replayed, roles)

    project = Project(id=ProjectId(new_id()), name=name, created_at=now)
    projects.add(project)
    memberships.grant(actor.user_id, project.id, CREATOR_ROLES, now)
    receipts.add(Receipt(actor.user_id, command.idempotency_key, project.id, fingerprint, now))
    return ProjectView(project, frozenset(CREATOR_ROLES), statuses_of([project.id])[project.id])


def rename_project(
    projects: ProjectStore,
    receipts: ReceiptStore,
    statuses_of: StatusReader,
    access: ProjectAccess,
    command: RenameProject,
    now: datetime,
) -> ProjectView:
    """Rename the project if `expected_revision` is still its revision.

    A retry with the same Idempotency-Key returns the project as it is now and does not check
    the revision again, which the first attempt already moved on.
    """
    access.require_any_role(Role.EDITOR, Role.APPROVER)
    name = normalize_name(command.name)
    project_id = access.project_id
    fingerprint = _fingerprint("rename", project_id, name, command.expected_revision)
    actor = access.actor
    if _replayed_project(receipts, actor, command.idempotency_key, fingerprint) is not None:
        return _view(projects, statuses_of, project_id, access.roles)

    project = _existing(projects, project_id)
    if project.revision != command.expected_revision:
        raise _changed(project.revision)
    # Saving an unchanged name would move the revision and invalidate other readers for nothing.
    if project.name != name:
        if not projects.rename(project_id, name, expected_revision=project.revision):
            raise _changed(None)
        project = replace(project, name=name, revision=project.revision + 1)
        # TODO(SSPOC-46): record a project.renamed audit event here, in this transaction.
    receipts.add(Receipt(actor.user_id, command.idempotency_key, project_id, fingerprint, now))
    return ProjectView(project, access.roles, statuses_of([project_id])[project_id])


def _view(
    projects: ProjectStore,
    statuses_of: StatusReader,
    project_id: ProjectId,
    roles: frozenset[Role],
) -> ProjectView:
    project = _existing(projects, project_id)
    return ProjectView(project, roles, statuses_of([project_id])[project_id])


def _existing(projects: ProjectStore, project_id: ProjectId) -> Project:
    project = projects.get(project_id)
    if project is None:
        raise NotFoundError("Project not found")
    return project


def _changed(current_revision: int | None) -> ProjectChangedError:
    details: dict[str, object] = (
        {} if current_revision is None else {"current_revision": current_revision}
    )
    return ProjectChangedError(
        "The project was changed since you opened it. Reload and try again.", details=details
    )


def _replayed_project(
    receipts: ReceiptStore, actor: Actor, idempotency_key: str, fingerprint: str
) -> ProjectId | None:
    receipt = receipts.find(actor.user_id, idempotency_key)
    if receipt is None:
        return None
    if receipt.fingerprint != fingerprint:
        raise IdempotencyKeyReusedError("This Idempotency-Key was already used for another request")
    return receipt.project_id


def _fingerprint(operation: str, project_id: ProjectId | None, *values: str | int) -> str:
    canonical = json.dumps([operation, None if project_id is None else str(project_id), *values])
    return hashlib.sha256(canonical.encode()).hexdigest()
