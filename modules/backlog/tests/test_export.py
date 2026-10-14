import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from markdown_it import MarkdownIt

from scopesteps.backlog.application.candidates import CitationChecker
from scopesteps.backlog.application.exporting import export_version
from scopesteps.backlog.domain.export import (
    ApprovedSnapshot,
    VersionNotApprovedError,
    approved_snapshot,
    escape_markdown,
    export_filename,
    require_approved,
    to_markdown,
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


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("Plain text, with a full stop.", "Plain text, with a full stop."),
        ("*bold* and _italic_", r"\*bold\* and \_italic\_"),
        ("# Not a heading", r"\# Not a heading"),
        ("- not a list", r"\- not a list"),
        ("+ not a list", r"\+ not a list"),
        ("1. not numbered", r"1\. not numbered"),
        ("2) not numbered", r"2\) not numbered"),
        ("> not a quote", r"\> not a quote"),
        ("=== not an underline", r"\=== not an underline"),
        ("<script>alert(1)</script>", r"\<script\>alert(1)\</script\>"),
        ("[a link](https://example.test)", r"\[a link\](https://example.test)"),
        ("![image](x.png)", r"!\[image\](x.png)"),
        ("`code`", r"\`code\`"),
        ("a | table | row", r"a \| table \| row"),
        ("~~struck~~", r"\~\~struck\~\~"),
        ("&amp; entity", r"\&amp; entity"),
        (r"a \ backslash", r"a \\ backslash"),
        ("first line\n# second line\n\n- third", r"first line \# second line - third"),
    ],
)
def test_markdown_escaping_keeps_text_literal(text: str, escaped: str) -> None:
    assert escape_markdown(text) == escaped


@pytest.mark.parametrize(
    "hostile",
    [
        "<img src=x onerror=alert(1)>",
        "[click](javascript:alert(1))",
        "**loud** _soft_ `code` ~~gone~~",
        "line\n# heading\n> quote\n- list\n1. numbered\n---\n| a | b |",
        "&lt;b&gt; &#x3C;i&#x3E;",
        "trailing #",
    ],
)
def test_text_from_sources_renders_as_plain_text(hostile: str) -> None:
    snapshot = _snapshot(replace(_version(), items=(replace(EPIC, title=hostile), STORY)))

    html = (
        MarkdownIt("commonmark")
        .enable("table")
        .enable("strikethrough")
        .render(to_markdown(snapshot))
    )

    heading = re.search(r"<h2>(.*?)</h2>", html)
    assert heading is not None
    assert not re.search(r"<(?!/?code>)[a-z]", heading.group(1)), "no markup inside the title"
    for tag in ("<img", "<a ", "<table", "<del", "<blockquote", "<hr"):
        assert tag not in html
    assert html.count("<h2>") == 3, "the epic, decisions and out of scope; nothing injected"


def test_markdown_carries_ids_origins_evidence_and_approval() -> None:
    markdown = to_markdown(_snapshot())

    assert markdown.startswith("# Room booking: approved backlog v2\n")
    assert f"- Version: `{UUID(int=40)}`, revision 3" in markdown
    assert f"- Approved by `{APPROVER}` at `2026-10-14T09:00:00Z`" in markdown
    assert f"- Based on: `{UUID(int=39)}`" in markdown
    assert "## Epic: Room booking" in markdown
    assert "### Story: Book a room" in markdown
    assert "As a student, I want to book a room.\n\nOnly free rooms are offered." in markdown
    assert f"1. A student books one slot. _(source: from the sources)_ `{UUID(int=10)}`" in markdown
    assert "_(human: confirmed by a reviewer)_" in markdown
    assert "_(proposed: agent suggestion, accepted)_" in markdown
    assert f"   - Confirmed by decision `{UUID(int=30)}`" in markdown
    assert (
        f"   - Evidence (supporting): source version `{SOURCE_VERSION}`, passage `{UUID(int=2)}`: "
        "“Students book one slot at a time.”"
    ) in markdown
    assert "- Answer: Up to one hour before the start." in markdown
    assert "- Excluded: Paying for rooms." in markdown
    assert "left out" not in markdown


def test_markdown_matches_the_reviewed_snapshot() -> None:
    expected = (Path(__file__).parent / "snapshots" / "approved-backlog.md").read_text()

    assert to_markdown(_snapshot()) == expected


def test_stories_follow_their_epic_whatever_the_stored_order() -> None:
    markdown = to_markdown(_snapshot(_version(STORY, EPIC)))

    assert markdown.index("Epic: Room booking") < markdown.index("Story: Book a room")


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
    assert "1 citation(s) left out" in to_markdown(snapshot)


@pytest.mark.parametrize(
    ("name", "number", "extension", "filename"),
    [
        ("Room booking", 2, "md", "room-booking-backlog-v2.md"),
        ('Café & Co. "Q4"', 1, "json", "cafe-co-q4-backlog-v1.json"),
        ("../../etc/passwd", 1, "json", "etc-passwd-backlog-v1.json"),
        ("请", 3, "md", "project-backlog-v3.md"),
        ("x" * 200, 1, "md", "x" * 60 + "-backlog-v1.md"),
        ("Room booking", None, "md", "room-booking-backlog.md"),
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
