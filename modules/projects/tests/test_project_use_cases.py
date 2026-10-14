from collections.abc import Collection, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from scopesteps.audit.client import (
    MAX_SUMMARY_CHARS,
    AuditActor,
    EventType,
    Subject,
    SubjectKind,
)
from scopesteps.backlog.client import ScopeState, ScopeStatus
from scopesteps.identity.client import Actor, ProjectAccess, ProjectRoles, Role, UserId
from scopesteps.kernel.errors import NotFoundError, PermissionDeniedError
from scopesteps.projects.application import projects as use_cases
from scopesteps.projects.application.projects import CreateProject, RenameProject
from scopesteps.projects.application.receipts import IdempotencyKeyReusedError, Receipt
from scopesteps.projects.client import ProjectId
from scopesteps.projects.domain.project import (
    MAX_NAME_CHARS,
    InvalidProjectNameError,
    Project,
    ProjectChangedError,
)

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
ACTOR = Actor(user_id=UserId(UUID(int=7)), display_name="Synthetic Reviewer")
NO_BASELINE = ScopeStatus(ScopeState.NO_BASELINE)


@dataclass(frozen=True)
class Recorded:
    project_id: ProjectId
    actor: AuditActor
    type: EventType
    subjects: tuple[Subject, ...]
    summary: str
    occurred_at: datetime


@dataclass
class World:
    """In-memory stand-ins for the project store, the receipts, identity, backlog and audit."""

    projects: dict[ProjectId, Project] = field(default_factory=dict[ProjectId, Project])
    receipts: list[Receipt] = field(default_factory=list[Receipt])
    roles: dict[ProjectId, frozenset[Role]] = field(
        default_factory=dict[ProjectId, frozenset[Role]]
    )
    status_reads: int = 0
    events: list[Recorded] = field(default_factory=list[Recorded])

    def record(
        self,
        *,
        project_id: ProjectId,
        actor: AuditActor,
        type: EventType,  # noqa: A002
        subjects: Sequence[Subject],
        summary: str,
        occurred_at: datetime,
    ) -> None:
        self.events.append(Recorded(project_id, actor, type, tuple(subjects), summary, occurred_at))

    def get(self, project_id: ProjectId) -> Project | None:
        return self.projects.get(project_id)

    def get_many(self, project_ids: Collection[ProjectId]) -> list[Project]:
        return [self.projects[project_id] for project_id in project_ids]

    def add(self, project: Project) -> None:
        self.projects[project.id] = project

    def rename(self, project_id: ProjectId, name: str, *, expected_revision: int) -> bool:
        project = self.projects[project_id]
        if project.revision != expected_revision:
            return False
        self.projects[project_id] = replace(project, name=name, revision=expected_revision + 1)
        return True

    def find(self, actor_id: UserId, idempotency_key: str) -> Receipt | None:
        return next(
            (
                receipt
                for receipt in self.receipts
                if (receipt.actor_id, receipt.idempotency_key) == (actor_id, idempotency_key)
            ),
            None,
        )

    def add_receipt(self, receipt: Receipt) -> None:
        self.receipts.append(receipt)

    def of_user(self, user_id: UserId) -> list[ProjectRoles]:
        return [ProjectRoles(project_id, roles) for project_id, roles in self.roles.items()]

    def grant(
        self, user_id: UserId, project_id: ProjectId, roles: Collection[Role], now: datetime
    ) -> None:
        self.roles[project_id] = self.roles.get(project_id, frozenset()) | frozenset(roles)

    def statuses_of(self, project_ids: Collection[ProjectId]) -> dict[ProjectId, ScopeStatus]:
        self.status_reads += 1
        return dict.fromkeys(project_ids, NO_BASELINE)

    def seed(self, name: str, *roles: Role, number: int = 1) -> ProjectId:
        project_id = ProjectId(UUID(int=number))
        self.projects[project_id] = Project(id=project_id, name=name, created_at=NOW)
        if roles:
            self.roles[project_id] = frozenset(roles)
        return project_id

    def access(self, project_id: ProjectId) -> ProjectAccess:
        return ProjectAccess(ACTOR, project_id, self.roles.get(project_id, frozenset()))


class Receipts:
    """Adapts the world to the ReceiptStore port, whose `add` would clash with the project's."""

    def __init__(self, world: World) -> None:
        self._world = world

    def find(self, actor_id: UserId, idempotency_key: str) -> Receipt | None:
        return self._world.find(actor_id, idempotency_key)

    def add(self, receipt: Receipt) -> None:
        self._world.add_receipt(receipt)


def _create(world: World, name: str, key: str = "create-key-0001") -> use_cases.ProjectView:
    return use_cases.create_project(
        world,
        Receipts(world),
        world,
        world.statuses_of,
        ACTOR,
        CreateProject(idempotency_key=key, name=name),
        NOW,
    )


def _rename(
    world: World,
    project_id: ProjectId,
    name: str,
    expected_revision: int = 1,
    key: str = "rename-key-0001",
) -> use_cases.ProjectView:
    return use_cases.rename_project(
        world,
        Receipts(world),
        world,
        world.statuses_of,
        world.access(project_id),
        RenameProject(idempotency_key=key, name=name, expected_revision=expected_revision),
        NOW,
    )


def test_the_creator_becomes_editor_and_approver() -> None:
    world = World()

    view = _create(world, "  Makerspace Tool Library ")

    assert view.project.name == "Makerspace Tool Library"
    assert view.project.revision == 1
    assert view.roles == {Role.EDITOR, Role.APPROVER}
    assert world.roles[view.project.id] == {Role.EDITOR, Role.APPROVER}
    assert view.status == NO_BASELINE


def test_repeating_a_create_returns_the_same_project() -> None:
    world = World()
    first = _create(world, "Makerspace Tool Library")

    second = _create(world, "Makerspace  Tool Library")

    assert second.project == first.project
    assert len(world.projects) == 1


def test_a_create_key_cannot_be_reused_for_another_name() -> None:
    world = World()
    _create(world, "Makerspace Tool Library")

    with pytest.raises(IdempotencyKeyReusedError):
        _create(world, "Library Kiosk Refresh")

    assert len(world.projects) == 1


def test_two_projects_may_share_a_name() -> None:
    world = World()

    first = _create(world, "Makerspace Tool Library", key="create-key-0001")
    second = _create(world, "Makerspace Tool Library", key="create-key-0002")

    assert first.project.id != second.project.id


def test_the_list_is_ordered_by_name_and_reads_statuses_once() -> None:
    world = World()
    world.seed("library kiosk", Role.VIEWER, number=1)
    world.seed("Campus Room Booking", Role.EDITOR, Role.APPROVER, number=2)
    world.seed("Makerspace Tool Library", Role.EDITOR, number=3)
    world.seed("Someone else's project", number=4)

    views = use_cases.list_projects(world, world, world.statuses_of, ACTOR)

    assert [view.project.name for view in views] == [
        "Campus Room Booking",
        "library kiosk",
        "Makerspace Tool Library",
    ]
    assert [view.roles for view in views] == [
        {Role.EDITOR, Role.APPROVER},
        {Role.VIEWER},
        {Role.EDITOR},
    ]
    assert world.status_reads == 1


def test_a_user_without_projects_gets_an_empty_list() -> None:
    world = World()

    assert use_cases.list_projects(world, world, world.statuses_of, ACTOR) == []
    assert world.status_reads == 0


@pytest.mark.parametrize("role", [Role.VIEWER, Role.EDITOR, Role.APPROVER])
def test_any_member_can_read_a_project(role: Role) -> None:
    world = World()
    project_id = world.seed("Campus Room Booking", role)

    view = use_cases.get_project(world, world.statuses_of, world.access(project_id))

    assert view.project.name == "Campus Room Booking"
    assert view.roles == {role}


def test_a_project_the_actor_is_not_in_is_not_found() -> None:
    world = World()
    project_id = world.seed("Campus Room Booking")

    with pytest.raises(NotFoundError):
        use_cases.get_project(world, world.statuses_of, world.access(project_id))
    with pytest.raises(NotFoundError):
        _rename(world, project_id, "Renamed")

    assert world.projects[project_id].name == "Campus Room Booking"


@pytest.mark.parametrize("role", [Role.EDITOR, Role.APPROVER])
def test_editors_and_approvers_can_rename(role: Role) -> None:
    world = World()
    project_id = world.seed("Campus Room Booking", role)

    view = _rename(world, project_id, " Campus Room  Booking 2027 ")

    assert view.project.name == "Campus Room Booking 2027"
    assert view.project.revision == 2
    assert world.projects[project_id] == view.project


@pytest.mark.parametrize("role", [Role.VIEWER, Role.INTEGRATION_ADMIN])
def test_other_roles_cannot_rename(role: Role) -> None:
    world = World()
    project_id = world.seed("Campus Room Booking", role)

    with pytest.raises(PermissionDeniedError):
        _rename(world, project_id, "Renamed")

    assert world.projects[project_id].name == "Campus Room Booking"


def test_a_stale_rename_changes_nothing_and_reports_the_current_revision() -> None:
    world = World()
    project_id = world.seed("Campus Room Booking", Role.EDITOR)
    _rename(world, project_id, "Campus Room Booking 2027")

    with pytest.raises(ProjectChangedError) as stale:
        _rename(world, project_id, "Study Rooms", expected_revision=1, key="rename-key-0002")

    assert stale.value.details == {"current_revision": 2}
    assert world.projects[project_id].name == "Campus Room Booking 2027"


def test_repeating_a_rename_returns_the_project_without_a_stale_error() -> None:
    world = World()
    project_id = world.seed("Campus Room Booking", Role.EDITOR)
    first = _rename(world, project_id, "Campus Room Booking 2027")

    second = _rename(world, project_id, "Campus Room Booking 2027")

    assert second.project == first.project
    assert second.project.revision == 2


def test_a_rename_key_cannot_be_reused_for_another_name() -> None:
    world = World()
    project_id = world.seed("Campus Room Booking", Role.EDITOR)
    _rename(world, project_id, "Campus Room Booking 2027")

    with pytest.raises(IdempotencyKeyReusedError):
        _rename(world, project_id, "Study Rooms", expected_revision=2)


def test_renaming_to_the_same_name_keeps_the_revision() -> None:
    world = World()
    project_id = world.seed("Campus Room Booking", Role.EDITOR)

    view = _rename(world, project_id, "  Campus Room Booking ")

    assert view.project.revision == 1


def test_a_rename_is_recorded_once_as_the_actors_action() -> None:
    world = World()
    project_id = world.seed("Campus Room Booking", Role.EDITOR)

    _rename(world, project_id, "Campus Room Booking 2027")
    _rename(world, project_id, "Campus Room Booking 2027")

    assert world.events == [
        Recorded(
            project_id,
            AuditActor.user(ACTOR),
            EventType.PROJECT_RENAMED,
            (Subject(SubjectKind.PROJECT, project_id),),
            'Renamed the project from "Campus Room Booking" to "Campus Room Booking 2027"',
            NOW,
        )
    ]


def test_renames_that_change_nothing_are_not_recorded() -> None:
    world = World()
    editable = world.seed("Campus Room Booking", Role.EDITOR, number=1)
    read_only = world.seed("Library Kiosk Refresh", Role.VIEWER, number=2)
    hidden = world.seed("Someone else's project", number=3)

    _rename(world, editable, " Campus Room Booking ")
    with pytest.raises(ProjectChangedError):
        _rename(world, editable, "Study Rooms", expected_revision=4, key="rename-key-0002")
    with pytest.raises(PermissionDeniedError):
        _rename(world, read_only, "Study Rooms", key="rename-key-0003")
    with pytest.raises(NotFoundError):
        _rename(world, hidden, "Study Rooms", key="rename-key-0004")
    with pytest.raises(InvalidProjectNameError):
        _rename(world, editable, "   ", key="rename-key-0005")

    assert world.events == []


def test_creating_a_project_records_no_event() -> None:
    world = World()

    _create(world, "Makerspace Tool Library")

    assert world.events == []


def test_the_summary_of_the_longest_rename_fits_the_activity_log() -> None:
    world = World()
    project_id = world.seed("a" * MAX_NAME_CHARS, Role.APPROVER)

    _rename(world, project_id, "b" * MAX_NAME_CHARS)

    assert len(world.events[0].summary) <= MAX_SUMMARY_CHARS
