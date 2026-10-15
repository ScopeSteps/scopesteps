from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from scopesteps.audit.client import AuditActor, EventType, Subject
from scopesteps.backlog.client import (
    BacklogVersionId,
    CheckCode,
    CheckResult,
    DecisionId,
    ScopeDecisionState,
    VersionChangedError,
    VersionNotDraftError,
    VersionState,
    VersionSummary,
)
from scopesteps.change_control.application.decisions import (
    Approve,
    Receipt,
    Reject,
    ScopeDecision,
    approve,
    reject,
)
from scopesteps.change_control.domain.change_request import (
    ChangeRequest,
    ChangeRequestStatus,
    ChangeSummary,
)
from scopesteps.change_control.domain.errors import (
    ApprovalBlockedError,
    BaselineChangedError,
    IdempotencyKeyReusedError,
    ScopeDecisionRequiredError,
    ScopeKeptError,
)
from scopesteps.change_control.domain.ids import ApprovalId, ChangeRequestId
from scopesteps.identity.client import Actor, ProjectAccess, Role, UserId
from scopesteps.kernel.errors import NotFoundError, PermissionDeniedError
from scopesteps.projects.client import ProjectId

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
PROJECT = ProjectId(UUID(int=1))
APPROVER = Actor(UserId(UUID(int=2)), "Sample Approver")
DRAFT = VersionSummary(
    id=BacklogVersionId(UUID(int=10)),
    project_id=PROJECT,
    base_version_id=None,
    revision=3,
    state=VersionState.DRAFT,
    content_hash="a" * 64,
    epics=1,
    stories=2,
)
APPROVE = Approve("approve-key-0001", 3, "a" * 64, None)
PASSED = tuple(CheckResult(code, passed=True) for code in CheckCode)


@dataclass
class FakeVersions:
    versions: dict[BacklogVersionId, VersionSummary]
    results: tuple[CheckResult, ...] = PASSED
    lost_race: bool = False
    """Whether the compare-and-set finds the version changed, as after a concurrent writer."""
    frozen: list[BacklogVersionId] = field(default_factory=list[BacklogVersionId])

    def summary(self, version_id: BacklogVersionId) -> VersionSummary | None:
        return self.versions.get(version_id)

    def checks(self, version_id: BacklogVersionId) -> tuple[CheckResult, ...]:
        return self.results

    def freeze(
        self,
        version_id: BacklogVersionId,
        *,
        expected_revision: int,
        content_hash: str,
        expected_state: VersionState,
    ) -> bool:
        return self._set(version_id, VersionState.APPROVED)

    def reject(
        self, version_id: BacklogVersionId, *, expected_revision: int, expected_state: VersionState
    ) -> bool:
        return self._set(version_id, VersionState.REJECTED)

    def _set(self, version_id: BacklogVersionId, state: VersionState) -> bool:
        if self.lost_race:
            return False
        self.versions[version_id] = replace(self.versions[version_id], state=state)
        self.frozen.append(version_id)
        return True


@dataclass
class FakeDecisions:
    decisions: list[ScopeDecision] = field(default_factory=list[ScopeDecision])
    receipts: list[Receipt] = field(default_factory=list[Receipt])

    def get(self, approval_id: ApprovalId) -> ScopeDecision | None:
        return next((d for d in self.decisions if d.id == approval_id), None)

    def current_baseline(self, project_id: ProjectId) -> ScopeDecision | None:
        approved = [d for d in self.decisions if d.baseline_number is not None]
        return max(approved, key=lambda d: d.baseline_number or 0, default=None)

    def add(self, decision: ScopeDecision) -> None:
        self.decisions.append(decision)

    def find_receipt(self, actor_id: UserId, idempotency_key: str) -> Receipt | None:
        return next((r for r in self.receipts if r.idempotency_key == idempotency_key), None)

    def add_receipt(self, receipt: Receipt) -> None:
        self.receipts.append(receipt)


@dataclass
class FakeRequests:
    requests: list[ChangeRequest] = field(default_factory=list[ChangeRequest])
    lost_race: bool = False

    def by_candidate(self, version_id: BacklogVersionId) -> ChangeRequest | None:
        return next((r for r in self.requests if r.candidate_version_id == version_id), None)

    def save(self, request: ChangeRequest, *, expected_revision: int) -> bool:
        if self.lost_race:
            return False
        self.requests = [request if r.id == request.id else r for r in self.requests]
        return True


@dataclass
class FakeAudit:
    events: list[tuple[EventType, str]] = field(default_factory=list[tuple[EventType, str]])

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
        self.events.append((type, summary))


class World:
    def __init__(self, *roles: Role, version: VersionSummary = DRAFT) -> None:
        self.versions = FakeVersions({version.id: version})
        self.decisions = FakeDecisions()
        self.requests = FakeRequests()
        self.audit = FakeAudit()
        self.roles = frozenset(roles)

    def resolve(self, project_id: ProjectId) -> ProjectAccess:
        return ProjectAccess(APPROVER, project_id, self.roles)

    def approve(self, command: Approve = APPROVE, version: VersionSummary = DRAFT) -> ScopeDecision:
        view = approve(
            self.versions,
            self.decisions,
            self.requests,
            self.audit,
            self.resolve,
            version.id,
            command,
            NOW,
        )
        return view.decision

    def reject(self, key: str = "reject-key-0001") -> ScopeDecision:
        command = Reject(key, DRAFT.revision, "Out of budget")
        return reject(
            self.versions,
            self.decisions,
            self.requests,
            self.audit,
            self.resolve,
            DRAFT.id,
            command,
            NOW,
        ).decision

    def nothing_recorded(self) -> bool:
        return not (self.versions.frozen or self.decisions.decisions or self.audit.events)


def test_an_approval_freezes_the_version_records_it_and_makes_baseline_v1() -> None:
    world = World(Role.APPROVER)

    decision = world.approve()

    assert (decision.decision, decision.baseline_number, decision.previous_baseline_id) == (
        "approved",
        1,
        None,
    )
    assert (decision.revision, decision.content_hash) == (3, "a" * 64)
    assert world.versions.frozen == [DRAFT.id]
    assert world.audit.events == [
        (
            EventType.BACKLOG_APPROVED,
            "Approved baseline v1 from draft revision 3, with 1 epic and 2 stories",
        )
    ]


def test_the_next_approval_must_build_on_the_current_baseline() -> None:
    world = World(Role.APPROVER)
    first = world.approve()
    change = replace(DRAFT, id=BacklogVersionId(UUID(int=11)), base_version_id=DRAFT.id)
    world.versions.versions[change.id] = change

    second = world.approve(Approve("approve-key-0002", 3, "a" * 64, first.version_id), change)

    assert (second.baseline_number, second.previous_baseline_id) == (2, DRAFT.id)


@pytest.mark.parametrize(
    ("roles", "error"),
    [
        ((), NotFoundError),
        ((Role.VIEWER,), PermissionDeniedError),
        ((Role.EDITOR,), PermissionDeniedError),
    ],
)
def test_only_an_approver_may_decide(roles: tuple[Role, ...], error: type[Exception]) -> None:
    world = World(*roles)

    with pytest.raises(error):
        world.approve()
    with pytest.raises(error):
        world.reject()

    assert world.nothing_recorded()


def test_a_failed_check_blocks_approval_and_reports_every_result() -> None:
    world = World(Role.APPROVER)
    world.versions.results = (
        *PASSED[:3],
        CheckResult(CheckCode.DECISIONS_RESOLVED, False, ("decision 1 is open",), 1),
    )

    with pytest.raises(ApprovalBlockedError) as blocked:
        world.approve()

    checks = blocked.value.details["checks"]
    assert isinstance(checks, list)
    assert len(checks) == 4  # pyright: ignore[reportUnknownArgumentType]
    assert world.nothing_recorded()


@pytest.mark.parametrize(
    "command",
    [replace(APPROVE, expected_revision=2), replace(APPROVE, content_hash="b" * 64)],
)
def test_a_stale_revision_or_hash_is_a_conflict(command: Approve) -> None:
    world = World(Role.APPROVER)

    with pytest.raises(VersionChangedError):
        world.approve(command)

    assert world.nothing_recorded()


def test_a_stale_baseline_is_a_conflict() -> None:
    world = World(Role.APPROVER)

    with pytest.raises(BaselineChangedError):
        world.approve(replace(APPROVE, expected_baseline_id=BacklogVersionId(UUID(int=99))))

    assert world.nothing_recorded()


def test_losing_the_compare_and_set_to_a_concurrent_writer_changes_nothing() -> None:
    world = World(Role.APPROVER)
    world.versions.lost_race = True

    with pytest.raises(VersionChangedError):
        world.approve()

    assert world.nothing_recorded()


def test_a_decided_version_cannot_be_decided_again() -> None:
    world = World(Role.APPROVER)
    world.approve()

    with pytest.raises(VersionNotDraftError):
        world.approve(replace(APPROVE, idempotency_key="approve-key-0002"))
    with pytest.raises(VersionNotDraftError):
        world.reject()

    assert len(world.decisions.decisions) == 1


def test_a_repeated_approval_returns_the_recorded_decision_without_acting_again() -> None:
    world = World(Role.APPROVER)
    first = world.approve()

    again = world.approve()

    assert again == first
    assert (len(world.versions.frozen), len(world.audit.events)) == (1, 1)


def test_reusing_a_key_for_another_command_is_a_conflict() -> None:
    world = World(Role.APPROVER)
    world.approve()

    with pytest.raises(IdempotencyKeyReusedError):
        world.reject(key=APPROVE.idempotency_key)


def test_a_rejection_keeps_the_baseline_and_its_reason_out_of_the_log() -> None:
    world = World(Role.APPROVER)

    decision = world.reject()

    assert (decision.decision, decision.baseline_number, decision.reason) == (
        "rejected",
        None,
        "Out of budget",
    )
    assert world.decisions.current_baseline(PROJECT) is None
    assert world.audit.events == [
        (EventType.BACKLOG_REJECTED, "Rejected draft revision 3; the baseline is unchanged")
    ]


BASELINE = replace(DRAFT, id=BacklogVersionId(UUID(int=20)), state=VersionState.APPROVED)
SCOPE = DecisionId(UUID(int=30))
CANDIDATE = replace(
    DRAFT,
    id=BacklogVersionId(UUID(int=21)),
    base_version_id=BASELINE.id,
    state=VersionState.IN_REVIEW,
    scope_decisions=(ScopeDecisionState(SCOPE, "reverse"),),
)
REQUEST = ChangeRequest(
    id=ChangeRequestId(UUID(int=40)),
    project_id=PROJECT,
    number=1,
    text="Add weekly bookings",
    requested_by=APPROVER.user_id,
    requested_by_name=APPROVER.display_name,
    requested_at=NOW,
    base_version_id=BASELINE.id,
    base_content_hash="b" * 64,
    source_version_id=UUID(int=50),
    run_id=UUID(int=60),
    status=ChangeRequestStatus.IN_REVIEW,
    revision=2,
    candidate_version_id=CANDIDATE.id,
    summary=ChangeSummary(1, 1, 0),
)
APPROVE_CHANGE = Approve("change-key-0001", 3, "a" * 64, BASELINE.id)


def _change_world(*roles: Role, candidate: VersionSummary = CANDIDATE) -> World:
    world = World(*roles, version=candidate)
    world.decisions.add(
        ScopeDecision(
            id=ApprovalId(UUID(int=70)),
            project_id=PROJECT,
            version_id=BASELINE.id,
            decision="approved",
            revision=1,
            content_hash="b" * 64,
            baseline_number=1,
            previous_baseline_id=None,
            reason=None,
            decided_by=APPROVER.user_id,
            decided_at=NOW,
        )
    )
    world.requests.requests.append(REQUEST)
    return world


def test_approving_a_change_candidate_makes_v2_and_approves_its_request() -> None:
    world = _change_world(Role.APPROVER)

    decision = world.approve(APPROVE_CHANGE, CANDIDATE)

    assert (decision.baseline_number, decision.previous_baseline_id) == (2, BASELINE.id)
    assert world.versions.frozen == [CANDIDATE.id]
    (request,) = world.requests.requests
    assert (request.status, request.revision) == (ChangeRequestStatus.APPROVED, 3)
    assert world.audit.events[-1] == (
        EventType.CHANGE_APPROVED,
        "Approved CR-1 as baseline v2 from candidate revision 3 (1 added, 1 changed, 0 removed), "
        "with 1 epic and 2 stories",
    )


def test_a_change_waits_for_every_scope_decision() -> None:
    open_scope = replace(CANDIDATE, scope_decisions=(ScopeDecisionState(SCOPE, None),))
    world = _change_world(Role.APPROVER, candidate=open_scope)

    with pytest.raises(ScopeDecisionRequiredError) as raised:
        world.approve(APPROVE_CHANGE, open_scope)

    assert raised.value.details == {"decision_ids": [str(SCOPE)]}
    assert not world.versions.frozen
    assert world.requests.requests == [REQUEST]


def test_kept_scope_leaves_only_rejection() -> None:
    kept = replace(CANDIDATE, scope_decisions=(ScopeDecisionState(SCOPE, "keep"),))
    world = _change_world(Role.APPROVER, candidate=kept)

    with pytest.raises(ScopeKeptError):
        world.approve(APPROVE_CHANGE, kept)
    view = reject(
        world.versions,
        world.decisions,
        world.requests,
        world.audit,
        world.resolve,
        kept.id,
        Reject("change-key-0002", 3, "Recurring bookings stay out"),
        NOW,
    )

    assert view.decision.decision == "rejected"
    assert view.current_baseline is not None
    assert view.current_baseline.version_id == BASELINE.id, "the baseline does not move"
    assert view.change_request is not None
    assert view.change_request.status is ChangeRequestStatus.REJECTED
    assert world.audit.events[-1] == (
        EventType.CHANGE_REJECTED,
        "Rejected CR-1 at candidate revision 3; the baseline is unchanged",
    )


def test_a_candidate_whose_request_is_not_in_review_cannot_be_decided() -> None:
    world = _change_world(Role.APPROVER)
    world.requests.requests = [replace(REQUEST, status=ChangeRequestStatus.APPROVED)]

    with pytest.raises(VersionNotDraftError):
        world.approve(APPROVE_CHANGE, CANDIDATE)
    assert not world.versions.frozen


def test_a_change_approved_against_a_stale_baseline_is_refused() -> None:
    world = _change_world(Role.APPROVER)

    with pytest.raises(BaselineChangedError):
        world.approve(Approve("change-key-0003", 3, "a" * 64, None), CANDIDATE)
    assert world.requests.requests == [REQUEST]


def test_only_an_approver_decides_a_change() -> None:
    world = _change_world(Role.EDITOR)

    with pytest.raises(PermissionDeniedError):
        world.approve(APPROVE_CHANGE, CANDIDATE)
    assert world.requests.requests == [REQUEST]
