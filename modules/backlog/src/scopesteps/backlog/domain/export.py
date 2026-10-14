"""An approved version as it is exported: the frozen snapshot, never a draft or the live state.

Rendering is pure, so the same snapshot always gives the same JSON fields and Markdown text.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

from scopesteps.backlog.domain.version import (
    BacklogVersion,
    ClaimOrigin,
    Criterion,
    Decision,
    Evidence,
    Item,
    ScopeNote,
    VersionState,
)
from scopesteps.backlog.domain.version_decision import VersionDecision
from scopesteps.kernel.errors import ConflictError

# Long enough to recognise the project, short enough for every file system's name limit.
MAX_FILENAME_SLUG_CHARS = 60

ORIGIN_LABELS: dict[ClaimOrigin, str] = {
    "source": "from the sources",
    "human": "confirmed by a reviewer",
    "proposed": "agent suggestion, accepted",
    "person": "written by a person",
}


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


# Every character that can start Markdown or HTML markup inside a line: emphasis, code, links and
# images (which need "["), raw HTML, entities, tables, strikethrough and a heading's closing "#".
# CommonMark lets any ASCII punctuation be escaped with a backslash, so this never changes the
# text shown.
_INLINE_MARKUP = re.compile(r"([\\`*_\[\]<>#|~&])")
# Markup that only counts at the start of a line: list markers, a setext underline, a numbered
# list ("1." or "1)") and a block quote are escaped there.
_LINE_START_MARKUP = re.compile(r"^(\s*)([-+=>]|\d+[.)])")


def escape_markdown(text: str) -> str:
    """Text shown literally in Markdown, on one line. Line breaks become spaces, so text from a
    source or a person can never start a heading, list, quote, table or HTML block."""
    line = " ".join(text.split())
    line = _INLINE_MARKUP.sub(r"\\\1", line)
    return _LINE_START_MARKUP.sub(_escape_line_start, line)


def _escape_line_start(match: re.Match[str]) -> str:
    marker = match.group(2)
    if marker[-1] in ".)":
        return f"{match.group(1)}{marker[:-1]}\\{marker[-1]}"
    return f"{match.group(1)}\\{marker}"


def _paragraphs(text: str) -> list[str]:
    return [escape_markdown(p) for p in re.split(r"\n\s*\n", text) if p.strip()]


def _code(value: object) -> str:
    # Only ids, hashes and timestamps go in code spans; none of them contains a backtick.
    return f"`{value}`"


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _evidence_lines(evidence: tuple[Evidence, ...], indent: str) -> list[str]:
    lines: list[str] = []
    for e in evidence:
        line = (
            f"{indent}- Evidence ({e.relationship}): source version {_code(e.source_version_id)}, "
            f"passage {_code(e.block_id)}"
        )
        if e.quote is not None:
            line += f": “{escape_markdown(e.quote)}”"
        lines.append(line)
    return lines


def _criterion_lines(number: int, criterion: Criterion) -> list[str]:
    label = ORIGIN_LABELS[criterion.origin]
    lines = [
        f"{number}. {escape_markdown(criterion.text)} _({criterion.origin}: {label})_ "
        f"{_code(criterion.id)}"
    ]
    if criterion.confirmed_by:
        decisions = ", ".join(_code(d) for d in criterion.confirmed_by)
        lines.append(f"   - Confirmed by decision {decisions}")
    lines += _evidence_lines(criterion.evidence, "   ")
    return lines


def _item_lines(item: Item, heading: str) -> list[str]:
    kind = "Epic" if item.kind == "epic" else "Story"
    lines = [f"{heading} {kind}: {escape_markdown(item.title)}", "", f"Id: {_code(item.id)}"]
    if item.human_edited:
        lines[-1] += " · edited by a person"
    lines.append("")
    for paragraph in _paragraphs(item.description):
        lines += [paragraph, ""]
    if item.criteria:
        lines += ["**Acceptance criteria**", ""]
        for number, criterion in enumerate(item.criteria, start=1):
            lines += _criterion_lines(number, criterion)
        lines.append("")
    for title, entries in (
        ("Assumptions", item.assumptions),
        ("Open questions", item.open_questions),
    ):
        if entries:
            lines += [f"**{title}**", "", *(f"- {escape_markdown(e)}" for e in entries), ""]
    return lines


def _ordered_items(items: tuple[Item, ...]) -> list[tuple[Item, str]]:
    """Each epic followed by its stories, in stored order; stories without an epic come last."""
    epics = [item for item in items if item.kind == "epic"]
    epic_ids = {epic.id for epic in epics}
    ordered: list[tuple[Item, str]] = []
    for epic in epics:
        ordered.append((epic, "##"))
        ordered += [(item, "###") for item in items if item.parent_id == epic.id]
    ordered += [
        (item, "##") for item in items if item.kind != "epic" and item.parent_id not in epic_ids
    ]
    return ordered


def _decision_lines(decision: Decision) -> list[str]:
    lines = [
        f"### {escape_markdown(decision.subject)}",
        "",
        f"- Id: {_code(decision.id)} ({decision.kind.replace('_', ' ')}, {decision.status})",
        f"- Question: {escape_markdown(decision.question)}",
        f"- Why it matters: {escape_markdown(decision.why_it_matters)}",
    ]
    if decision.answer is not None:
        lines.append(f"- Answer: {escape_markdown(decision.answer)}")
    if decision.decided_by is not None and decision.decided_at is not None:
        lines.append(
            f"- Decided by {_code(decision.decided_by)} at {_code(_timestamp(decision.decided_at))}"
        )
    if decision.affected_item_ids:
        lines.append(f"- Affects: {', '.join(_code(i) for i in decision.affected_item_ids)}")
    return [*lines, *_evidence_lines(decision.evidence, ""), ""]


def _scope_note_lines(note: ScopeNote) -> list[str]:
    kind = "Excluded" if note.kind == "excluded" else "Suggested, not included"
    return [f"- {kind}: {escape_markdown(note.summary)}", *_evidence_lines(note.evidence, "  ")]


def to_markdown(snapshot: ApprovedSnapshot) -> str:
    version, approval = snapshot.version, snapshot.approval
    number = "" if approval.baseline_number is None else f" v{approval.baseline_number}"
    sources = ", ".join(_code(v) for v in version.source_version_ids) or "none"
    lines = [
        f"# {escape_markdown(snapshot.project_name)}: approved backlog{number}",
        "",
        f"- Version: {_code(version.id)}, revision {version.revision}",
        f"- Approved by {_code(approval.decided_by)} at {_code(_timestamp(approval.decided_at))}",
        f"- Content hash: {_code(version.content_hash)}",
        "- Based on: "
        + (
            "no earlier version"
            if version.base_version_id is None
            else _code(version.base_version_id)
        ),
        f"- Sources: {sources}",
        f"- Exported at {_code(_timestamp(snapshot.exported_at))}",
    ]
    if snapshot.withheld_evidence:
        lines.append(
            f"- {snapshot.withheld_evidence} citation(s) left out: they no longer resolve to a "
            "passage this project holds"
        )
    lines.append("")
    for item, heading in _ordered_items(version.items):
        lines += _item_lines(item, heading)
    if version.decisions:
        lines += ["## Decisions", ""]
        for decision in version.decisions:
            lines += _decision_lines(decision)
    if version.out_of_scope:
        lines += ["## Out of scope", ""]
        for note in version.out_of_scope:
            lines += _scope_note_lines(note)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
