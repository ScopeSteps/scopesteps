"""The checks a draft must pass before it can be approved. Approval runs them again itself: what
a reviewer saw earlier is never trusted."""

from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from scopesteps.backlog.domain.version import (
    MAX_EPICS,
    MAX_STORIES,
    MAX_TITLE_CHARS,
    BacklogVersion,
    Evidence,
    approved_content,
)

MAX_REPORTED_PROBLEMS = 10


class CheckCode(StrEnum):
    STRUCTURE_VALID = "structure_valid"
    CITATIONS_RESOLVE = "citations_resolve"
    SUGGESTIONS_REVIEWED = "suggestions_reviewed"
    DECISIONS_RESOLVED = "decisions_resolved"


CHECK_TITLES = {
    CheckCode.STRUCTURE_VALID: "Structure is valid",
    CheckCode.CITATIONS_RESOLVE: "Every citation resolves",
    CheckCode.SUGGESTIONS_REVIEWED: "Every agent suggestion is reviewed",
    CheckCode.DECISIONS_RESOLVED: "No decision is open",
}


@dataclass(frozen=True)
class CheckResult:
    code: CheckCode
    passed: bool
    problems: tuple[str, ...] = ()
    """At most MAX_REPORTED_PROBLEMS, each naming ids and counts only."""
    problem_count: int = 0

    @property
    def title(self) -> str:
        return CHECK_TITLES[self.code]


def structure_problems(version: BacklogVersion) -> list[str]:
    """Ids, hierarchy, ceilings and references in the content approval would freeze."""
    items = approved_content(version.items)
    problems: list[str] = []
    item_ids = Counter(item.id for item in items)
    problems += [f"item {i} appears {n} times" for i, n in item_ids.items() if n > 1]
    epics = {item.id for item in items if item.kind == "epic"}
    stories = len(items) - len(epics)
    if len(epics) > MAX_EPICS:
        problems.append(f"{len(epics)} epics exceed the limit of {MAX_EPICS}")
    if stories > MAX_STORIES:
        problems.append(f"{stories} stories exceed the limit of {MAX_STORIES}")
    if not items:
        problems.append("the backlog has no items")
    for item in items:
        if not item.title.strip() or len(item.title) > MAX_TITLE_CHARS:
            problems.append(f"item {item.id} needs a title of 1 to {MAX_TITLE_CHARS} characters")
        if item.kind == "epic" and item.parent_id is not None:
            problems.append(f"epic {item.id} has a parent")
        if item.kind == "story" and item.parent_id not in epics:
            problems.append(f"story {item.id} belongs to no epic")
        if any(not criterion.text.strip() for criterion in item.criteria):
            problems.append(f"item {item.id} has an empty criterion")
    criterion_ids = Counter(c.id for item in items for c in item.criteria)
    problems += [f"criterion {i} appears {n} times" for i, n in criterion_ids.items() if n > 1]
    decision_ids = {decision.id for decision in version.decisions}
    for decision in version.decisions:
        unknown = [str(i) for i in decision.affected_item_ids if i not in item_ids]
        if unknown:
            problems.append(f"decision {decision.id} affects unknown items {', '.join(unknown)}")
    for item in items:
        for criterion in item.criteria:
            unknown = [str(d) for d in criterion.confirmed_by if d not in decision_ids]
            if unknown:
                problems.append(
                    f"criterion {criterion.id} is confirmed by unknown decisions {', '.join(unknown)}"
                )
    return problems


def cited_evidence(version: BacklogVersion) -> list[Evidence]:
    """Every passage the approved content would cite, each once."""
    evidence = [
        *(e for item in approved_content(version.items) for c in item.criteria for e in c.evidence),
        *(e for decision in version.decisions for e in decision.evidence),
        *(e for note in version.out_of_scope for e in note.evidence),
    ]
    return list(dict.fromkeys(evidence))


def cites_any(version: BacklogVersion, source_version_ids: Collection[UUID]) -> bool:
    """Whether the version was made from, or anywhere cites, one of the source versions.

    Counts rejected suggestions too: what a draft stored keeps its provenance.
    """
    wanted = set(source_version_ids)
    evidence = (
        *(e for item in version.items for c in item.criteria for e in c.evidence),
        *(e for decision in version.decisions for e in decision.evidence),
        *(e for note in version.out_of_scope for e in note.evidence),
    )
    return bool(wanted & set(version.source_version_ids)) or any(
        e.source_version_id in wanted for e in evidence
    )


def unpinned_citations(version: BacklogVersion) -> list[str]:
    """Evidence may cite only the source versions the draft was made from."""
    pinned = set(version.source_version_ids)
    unpinned = sorted(
        {str(e.source_version_id) for e in cited_evidence(version)} - {str(v) for v in pinned}
    )
    return [
        f"evidence cites source version {v}, which the draft was not made from" for v in unpinned
    ]


def review_checks(
    version: BacklogVersion, citation_problems: Sequence[str]
) -> tuple[CheckResult, ...]:
    """Every check, passed or not, in a fixed order. `citation_problems` are the citations that
    do not resolve to a stored passage, as the evidence module reported them."""
    pending = [
        f"criterion {criterion.id} on item {item.id} is an unreviewed agent suggestion"
        for item in version.items
        for criterion in item.criteria
        if criterion.suggestion == "pending"
    ]
    open_decisions = [
        f"decision {decision.id} is {decision.status}"
        for decision in version.decisions
        if not decision.is_resolved
    ]
    found = {
        CheckCode.STRUCTURE_VALID: structure_problems(version),
        CheckCode.CITATIONS_RESOLVE: [*unpinned_citations(version), *citation_problems],
        CheckCode.SUGGESTIONS_REVIEWED: pending,
        CheckCode.DECISIONS_RESOLVED: open_decisions,
    }
    return tuple(
        CheckResult(
            code=code,
            passed=not problems,
            problems=tuple(problems[:MAX_REPORTED_PROBLEMS]),
            problem_count=len(problems),
        )
        for code, problems in found.items()
    )
