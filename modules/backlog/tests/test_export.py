import csv
import io
from collections.abc import Collection, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from scopesteps.backlog.application.candidates import CitationChecker
from scopesteps.backlog.application.exporting import export_version
from scopesteps.backlog.domain.export import (
    MAX_SUMMARY_CHARS,
    ApprovedSnapshot,
    VersionNotApprovedError,
    approved_snapshot,
    export_filename,
    jira_summary,
    require_approved,
    to_jira_csv,
)
from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, DecisionId, ItemId
from scopesteps.backlog.domain.version import (
    BacklogVersion,
    Criterion,
    Decision,
    Evidence,
    Item,
    ScopeNote,
    VersionState,
    content_hash,
)
from scopesteps.backlog.domain.version_decision import DecisionReader, VersionDecision
from scopesteps.evidence.client import Citation, InvalidCitation
from scopesteps.identity.client import Actor, ProjectAccess, ProjectAccessResolver, Role, UserId
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectId, ProjectRef

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
APPROVER = UserId(UUID(int=8))
PROJECT = ProjectId(UUID(int=9))
SOURCE_VERSION = UUID(int=1)
PASSAGE = Evidence(SOURCE_VERSION, UUID(int=2), "Students book one slot at a time.")
GONE = Evidence(SOURCE_VERSION, UUID(int=3))
EPIC = Item(ItemId(UUID(int=20)), "epic", None, "Room booking", "Booking rooms.")
STORY = Item(
    ItemId(UUID(int=21)),
    "story",
    EPIC.id,
    "Book a room",
    "As a student, I want to book a room.\n\nOnly free rooms are offered.",
    criteria=(
        Criterion(CriterionId(UUID(int=10)), "A student books one slot.", "source", (PASSAGE,)),
        Criterion(
            CriterionId(UUID(int=11)),
            "Cancelling is allowed up to one hour before.",
            "human",
            (GONE,),
            confirmed_by=(DecisionId(UUID(int=30)),),
        ),
        Criterion(
            CriterionId(UUID(int=12)), "A confirmation is shown.", "proposed", suggestion="accepted"
        ),
    ),
    assumptions=("Rooms have fixed slots.",),
)
ANSWERED = Decision(
    DecisionId(UUID(int=30)),
    "missing_decision",
    "answered",
    "Cancellation",
    "How late may a user cancel?",
    "No rule is agreed.",
    affected_item_ids=(STORY.id,),
    answer="Up to one hour before the start.",
    decided_by=APPROVER,
    decided_at=NOW,
)
APPROVAL = VersionDecision(BacklogVersionId(UUID(int=40)), "approved", APPROVER, NOW, 2)


def _version(
    *items: Item, state: VersionState = VersionState.APPROVED, project: ProjectId = PROJECT
) -> BacklogVersion:
    items = items or (EPIC, STORY)
    return BacklogVersion(
        id=BacklogVersionId(UUID(int=40)),
        project_id=project,
        base_version_id=BacklogVersionId(UUID(int=39)),
        revision=3,
        state=state,
        content_hash=content_hash(items, (ANSWERED,), ()),
        run_id=None,
        source_version_ids=(SOURCE_VERSION,),
        items=items,
        decisions=(ANSWERED,),
        out_of_scope=(ScopeNote("excluded", "Paying for rooms.", (PASSAGE,)),),
        created_by=APPROVER,
        created_at=NOW,
    )


def _snapshot(
    version: BacklogVersion | None = None, name: str = "Room booking"
) -> ApprovedSnapshot:
    return approved_snapshot(
        version or _version(),
        APPROVAL,
        project_name=name,
        exported_at=NOW,
        permitted=lambda _: True,
    )


TRICKY_EPIC = Item(
    ItemId(UUID(int=22)),
    "epic",
    None,
    'Rooms, desks and "quiet" zones',
    "Booking every kind of space.\r\nIncluding desks, which have no doors.",
)
# Exactly 300 characters, ending mid-word.
LONG_TITLE = ("Book a quiet room for a group of students " * 8)[:300]
TRICKY_STORY = Item(
    ItemId(UUID(int=23)),
    "story",
    TRICKY_EPIC.id,
    LONG_TITLE,
    '=HYPERLINK("https://example.test")\n\n\n\nThen the second paragraph.',
    criteria=(
        Criterion(CriterionId(UUID(int=13)), "予約は一度に一枠です。", "source", (PASSAGE,)),
        Criterion(CriterionId(UUID(int=14)), '회의실, "예약"\n및 취소.', "person"),
    ),
    open_questions=("@Dana: can a desk be shared?",),
)
ORPHAN = Item(ItemId(UUID(int=24)), "story", ItemId(UUID(int=99)), "Lost story", "")


def _rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text, newline="")))


def test_csv_has_the_five_jira_columns_with_stories_after_their_epic() -> None:
    rows = _rows(to_jira_csv(_snapshot(_version(STORY, TRICKY_STORY, EPIC, TRICKY_EPIC))))

    assert rows[0] == ["Issue ID", "Issue Type", "Summary", "Description", "Parent"]
    assert [(r[0], r[1], r[2][:20], r[4]) for r in rows[1:]] == [
        ("1", "Epic", "Room booking", ""),
        ("2", "Story", "Book a room", "1"),
        ("3", "Epic", 'Rooms, desks and "qu', ""),
        ("4", "Story", "Book a quiet room fo", "3"),
    ]


def test_a_story_whose_epic_is_missing_is_kept_with_an_empty_parent() -> None:
    rows = _rows(to_jira_csv(_snapshot(_version(ORPHAN, EPIC, STORY))))

    assert [(r[0], r[1], r[2], r[4]) for r in rows[1:]] == [
        ("1", "Epic", "Room booking", ""),
        ("2", "Story", "Book a room", "1"),
        ("3", "Story", "Lost story", ""),
    ]


def test_description_sections_appear_in_order_only_when_they_have_content() -> None:
    story = replace(STORY, open_questions=("Can a group book?",))

    rows = _rows(to_jira_csv(_snapshot(_version(EPIC, story))))

    assert rows[1][3] == "Booking rooms."
    assert rows[2][3] == (
        "As a student, I want to book a room.\n\nOnly free rooms are offered.\n\n"
        "Acceptance criteria\n- A student books one slot.\n"
        "- Cancelling is allowed up to one hour before.\n- A confirmation is shown.\n\n"
        "Assumptions\n- Rooms have fixed slots.\n\n"
        "Open questions\n- Can a group book?"
    )


def test_an_item_with_only_criteria_starts_with_them() -> None:
    story = replace(STORY, description="  ", assumptions=())

    rows = _rows(to_jira_csv(_snapshot(_version(EPIC, story))))

    assert rows[2][3].startswith("Acceptance criteria\n- A student books one slot.")


def test_csv_matches_the_reviewed_snapshot() -> None:
    expected = (Path(__file__).parent / "snapshots" / "approved-backlog.csv").read_bytes()

    rendered = to_jira_csv(_snapshot(_version(EPIC, STORY, TRICKY_EPIC, TRICKY_STORY, ORPHAN)))

    assert rendered.encode() == expected


def test_csv_file_rules_hold() -> None:
    data = to_jira_csv(_snapshot(_version(EPIC, STORY, TRICKY_EPIC, TRICKY_STORY))).encode()

    assert not data.startswith(b"\xef\xbb\xbf"), "no byte-order mark"
    assert data.endswith(b"\r\n")
    assert data.count(b"\r\n") == 5, "one CRLF per row; line breaks inside cells are LF"
    assert b"\r" not in data.replace(b"\r\n", b"")
    assert data.decode("utf-8")


def test_the_same_snapshot_always_renders_the_same_bytes() -> None:
    version = _version(EPIC, STORY, TRICKY_EPIC, TRICKY_STORY, ORPHAN)

    renders = {
        to_jira_csv(
            approved_snapshot(
                version, APPROVAL, project_name=name, exported_at=at, permitted=lambda _: True
            )
        ).encode()
        for name, at in (("Room booking", NOW), ("Renamed", NOW.replace(year=2027)))
    }

    assert len(renders) == 1


def test_csv_leaves_out_evidence_origins_ids_hashes_and_approval() -> None:
    version = _version()
    snapshot = _snapshot(version)

    text = to_jira_csv(snapshot)

    forbidden = [
        str(version.id),
        str(version.base_version_id),
        version.content_hash,
        str(SOURCE_VERSION),
        str(PASSAGE.block_id),
        str(APPROVER),
        str(PROJECT),
        "2026-10-14",
        *(str(item.id) for item in version.items),
        *(str(c.id) for item in version.items for c in item.criteria),
        *(str(d.id) for d in version.decisions),
        PASSAGE.quote or "",
        "Students book one slot at a time.",
        "supporting",
        "from the sources",
        "confirmed by a reviewer",
        "source",
        "proposed",
        "Cancellation",
        "How late may a user cancel?",
        "Paying for rooms.",
    ]
    for value in forbidden:
        assert value not in text, value


@pytest.mark.parametrize(
    "start", ["=", "+", "-", "@", "\t", "\r", "\uff1d", "\uff0b", "\uff0d", "\uff20"]
)
def test_cells_that_could_start_a_formula_get_a_leading_apostrophe(start: str) -> None:
    epic = replace(EPIC, title=f"{start}SUM(A1)", description=f"{start}1+1 is two.")
    story = replace(STORY, description=f"{start}cmd", criteria=(), assumptions=())

    rows = _rows(to_jira_csv(_snapshot(_version(epic, story))))

    if start.isspace():
        assert rows[1][2] == "SUM(A1)", "a title is one line, so leading white space goes"
        assert rows[1][3] == "1+1 is two."
    else:
        assert rows[1][2] == f"'{start}SUM(A1)"
        assert rows[1][3] == f"'{start}1+1 is two."
        assert rows[2][3] == f"'{start}cmd"


def test_white_space_cannot_hide_a_formula() -> None:
    epic = replace(EPIC, title="\t =1+1", description="\r\n\t@SUM(A1)")

    rows = _rows(to_jira_csv(_snapshot(_version(epic))))

    assert (rows[1][2], rows[1][3]) == ("'=1+1", "'@SUM(A1)")


@pytest.mark.parametrize(
    ("title", "summary"),
    [
        ("Book a room", "Book a room"),
        ("  Book\n a\troom  ", "Book a room"),
        ("x" * 255, "x" * 255),
        ("x" * 256, "x" * 254 + "…"),
        ("word " * 60, ("word " * 51).rstrip() + "…"),
        (("a" * 253) + " bc", ("a" * 253) + "…"),
        (("a" * 254) + " bc", ("a" * 254) + "…"),
        ("=" + "y" * 300, "'=" + "y" * 252 + "…"),
        ("😀" * 128, "😀" * 127 + "…"),
    ],
)
def test_summary_fits_jira_and_is_cut_at_a_word(title: str, summary: str) -> None:
    assert jira_summary(title) == summary
    assert len(summary.encode("utf-16-le")) // 2 <= MAX_SUMMARY_CHARS


@pytest.mark.parametrize(
    "state", [VersionState.DRAFT, VersionState.IN_REVIEW, VersionState.REJECTED]
)
def test_only_an_approved_version_is_exported(state: VersionState) -> None:
    with pytest.raises(VersionNotApprovedError) as raised:
        require_approved(_version(state=state), APPROVAL)

    assert raised.value.details == {"state": state.value}


def test_an_approved_version_without_its_approval_is_not_exported() -> None:
    with pytest.raises(VersionNotApprovedError):
        require_approved(_version(), None)


def test_evidence_that_is_not_permitted_is_left_out_and_counted() -> None:
    snapshot = approved_snapshot(
        _version(), APPROVAL, project_name="P", exported_at=NOW, permitted=lambda e: e != GONE
    )

    cancelling = snapshot.version.items[1].criteria[1]
    assert (cancelling.evidence, snapshot.withheld_evidence) == ((), 1)
    assert snapshot.version.items[1].criteria[0].evidence == (PASSAGE,)


@pytest.mark.parametrize(
    ("name", "number", "extension", "filename"),
    [
        ("Room booking", 2, "csv", "room-booking-backlog-v2.csv"),
        ('Café & Co. "Q4"', 1, "json", "cafe-co-q4-backlog-v1.json"),
        ("../../etc/passwd", 1, "json", "etc-passwd-backlog-v1.json"),
        ("请", 3, "csv", "project-backlog-v3.csv"),
        ("x" * 200, 1, "csv", "x" * 60 + "-backlog-v1.csv"),
        ("Room booking", None, "csv", "room-booking-backlog.csv"),
    ],
)
def test_download_names_are_safe(
    name: str, number: int | None, extension: str, filename: str
) -> None:
    assert export_filename(name, number, extension) == filename


class Versions:
    def __init__(self, *versions: BacklogVersion) -> None:
        self.versions = {version.id: version for version in versions}

    def get(self, version_id: BacklogVersionId) -> BacklogVersion | None:
        return self.versions.get(version_id)

    def find_by_run(self, run_id: UUID) -> BacklogVersion | None:
        return None

    def add(self, version: BacklogVersion) -> None:
        self.versions[version.id] = version


def _resolver(*roles: Role) -> ProjectAccessResolver:
    actor = Actor(APPROVER, "Avery")
    return lambda project_id: ProjectAccess(actor, project_id, frozenset(roles))


def _reader(*decisions: VersionDecision) -> DecisionReader:
    def read(ids: Collection[BacklogVersionId]) -> Mapping[BacklogVersionId, VersionDecision]:
        return {d.version_id: d for d in decisions if d.version_id in ids}

    return read


def _citations_without(gone: Evidence) -> CitationChecker:
    def check(project_id: ProjectId, citations: Sequence[Citation]) -> list[InvalidCitation]:
        return [
            InvalidCitation(c, "unknown_block") for c in citations if c.block_id == gone.block_id
        ]

    return check


def _export(
    version: BacklogVersion, *roles: Role, decisions: tuple[VersionDecision, ...] = (APPROVAL,)
) -> ApprovedSnapshot:
    return export_version(
        Versions(version),
        _resolver(*roles),
        _reader(*decisions),
        lambda project_id: ProjectRef(project_id, "Room booking"),
        _citations_without(GONE),
        version.id,
        NOW,
    )


def test_a_viewer_exports_the_stored_version_with_evidence_checked_again() -> None:
    snapshot = _export(_version(), Role.VIEWER)

    assert snapshot.version.id == UUID(int=40)
    assert (snapshot.project_name, snapshot.approval, snapshot.withheld_evidence) == (
        "Room booking",
        APPROVAL,
        1,
    )


@pytest.mark.parametrize("state", [VersionState.APPROVED, VersionState.DRAFT])
def test_a_non_member_cannot_tell_a_version_exists(state: VersionState) -> None:
    with pytest.raises(NotFoundError):
        _export(_version(state=state))


def test_a_member_cannot_export_a_draft() -> None:
    with pytest.raises(VersionNotApprovedError):
        _export(_version(state=VersionState.DRAFT), Role.EDITOR, decisions=())
