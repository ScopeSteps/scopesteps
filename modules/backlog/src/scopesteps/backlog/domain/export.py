"""An approved version as it is exported: the frozen snapshot, never a draft or the live state.

Rendering is pure, so the same snapshot always gives the same JSON fields and CSV bytes.
"""

import csv
import io
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

from scopesteps.backlog.domain.ids import ItemId
from scopesteps.backlog.domain.version import BacklogVersion, Evidence, Item, VersionState
from scopesteps.backlog.domain.version_decision import VersionDecision
from scopesteps.kernel.errors import ConflictError

# Long enough to recognise the project, short enough for every file system's name limit.
MAX_FILENAME_SLUG_CHARS = 60


class VersionNotApprovedError(ConflictError):
    """Only an approved version is exported: a draft must never pass for an approved backlog."""

    code = "VERSION_NOT_APPROVED"


@dataclass(frozen=True)
class ApprovedSnapshot:
    version: BacklogVersion
    approval: VersionDecision
    project_name: str
    exported_at: datetime
    withheld_evidence: int
    """Citations left out because they no longer resolve to a passage the project holds."""


def require_approved(version: BacklogVersion, approval: VersionDecision | None) -> VersionDecision:
    """The approval of `version`. Raises VersionNotApprovedError for a draft, a candidate in
    review or a rejected version, so none of them can pass for an approved backlog."""
    if (
        version.state is not VersionState.APPROVED
        or approval is None
        or approval.decision != "approved"
    ):
        raise VersionNotApprovedError(
            "Only an approved backlog version can be exported.",
            details={"state": version.state.value},
        )
    return approval


def approved_snapshot(
    version: BacklogVersion,
    approval: VersionDecision,
    *,
    project_name: str,
    exported_at: datetime,
    permitted: Callable[[Evidence], bool],
) -> ApprovedSnapshot:
    """The version as stored when it was approved, with only the evidence `permitted` allows."""
    withheld = 0

    def keep(evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
        nonlocal withheld
        kept = tuple(e for e in evidence if permitted(e))
        withheld += len(evidence) - len(kept)
        return kept

    filtered = replace(
        version,
        items=tuple(
            replace(
                item,
                criteria=tuple(replace(c, evidence=keep(c.evidence)) for c in item.criteria),
            )
            for item in version.items
        ),
        decisions=tuple(replace(d, evidence=keep(d.evidence)) for d in version.decisions),
        out_of_scope=tuple(replace(n, evidence=keep(n.evidence)) for n in version.out_of_scope),
    )
    return ApprovedSnapshot(filtered, approval, project_name, exported_at, withheld)


def export_filename(project_name: str, baseline_number: int | None, extension: str) -> str:
    """A download name that is safe in a header and on any file system: ASCII letters, digits
    and hyphens, then the version number."""
    ascii_name = unicodedata.normalize("NFKD", project_name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    slug = slug[:MAX_FILENAME_SLUG_CHARS].rstrip("-") or "project"
    number = "" if baseline_number is None else f"-v{baseline_number}"
    return f"{slug}-backlog{number}.{extension}"


JIRA_CSV_COLUMNS = ("Issue ID", "Issue Type", "Summary", "Description", "Parent")

# Jira's limit on a summary, counted in UTF-16 code units as Jira counts it.
MAX_SUMMARY_CHARS = 255

# A spreadsheet treats a cell starting with one of these as a formula (OWASP CSV injection),
# including the full-width forms some spreadsheets fold to ASCII.
_FORMULA_START = frozenset("=+-@\t\r\uff1d\uff0b\uff0d\uff20")


def to_jira_csv(snapshot: ApprovedSnapshot) -> str:
    """The approved epics and stories in the Jira Cloud CSV importer's hierarchy layout (ADR 0014).

    Each epic is followed by its stories. Issue IDs are numbered in that order and exist only to
    link a story to its epic's row; a story whose epic is not in the version has an empty Parent.
    Only what a Jira issue needs is written: no evidence, origins, ids, hashes or approval.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(JIRA_CSV_COLUMNS)
    issue_ids: dict[ItemId, str] = {}
    for number, item in enumerate(_epics_then_stories(snapshot.version.items), start=1):
        issue_id = str(number)
        if item.kind == "epic":
            issue_ids[item.id] = issue_id
        parent = "" if item.parent_id is None else issue_ids.get(item.parent_id, "")
        writer.writerow(
            (
                issue_id,
                "Epic" if item.kind == "epic" else "Story",
                jira_summary(item.title),
                _neutralise(_description(item)),
                parent if item.kind == "story" else "",
            )
        )
    return buffer.getvalue()


def jira_summary(title: str) -> str:
    """The title on one line, safe from formula injection, cut at a word to fit Jira's limit."""
    summary = _neutralise(" ".join(title.split()))
    if _utf16_length(summary) <= MAX_SUMMARY_CHARS:
        return summary
    room = MAX_SUMMARY_CHARS - 1
    cut = ""
    for char in summary:
        if _utf16_length(cut + char) > room:
            break
        cut += char
    # Back up to the last whole word, unless the title is one word too long to fit.
    whole_words, space, _ = cut.rpartition(" ")
    if not summary[len(cut)].isspace() and space and whole_words.strip():
        cut = whole_words
    return cut.rstrip() + "…"


def _description(item: Item) -> str:
    sections = [_plain(item.description)]
    for heading, entries in (
        ("Acceptance criteria", tuple(c.text for c in item.criteria)),
        ("Assumptions", item.assumptions),
        ("Open questions", item.open_questions),
    ):
        lines = [f"- {' '.join(entry.split())}" for entry in entries if entry.strip()]
        if lines:
            sections.append("\n".join([heading, *lines]))
    return "\n\n".join(section for section in sections if section)


def _plain(text: str) -> str:
    """Text with its paragraphs kept and every line break written as one LF."""
    lines = (line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _neutralise(cell: str) -> str:
    return f"'{cell}" if cell[:1] in _FORMULA_START else cell


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _epics_then_stories(items: tuple[Item, ...]) -> list[Item]:
    """Each epic followed by its stories, in stored order; stories without an epic come last."""
    epics = [item for item in items if item.kind == "epic"]
    epic_ids = {epic.id for epic in epics}
    ordered: list[Item] = []
    for epic in epics:
        ordered += [epic, *(i for i in items if i.kind != "epic" and i.parent_id == epic.id)]
    return ordered + [i for i in items if i.kind != "epic" and i.parent_id not in epic_ids]
