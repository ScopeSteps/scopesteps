"""Deterministic checks on a schema-valid draft. Prompts are not relied on for these guarantees.

They feed the repair attempt during drafting and later back the agent's `validate_backlog` tool,
so the single-pass baseline and the agent are held to the same rules.
"""

import re
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from scopesteps.agent.application.schemas import (
    AnyDraft,
    Citation,
    DraftBacklog,
    DraftBacklogV1,
    DraftBacklogV3,
    DraftBacklogV4,
    SourceBlockInput,
    SpeakerNote,
    Statement,
)
from scopesteps.agent.application.speakers import describe_speakers
from scopesteps.projects.client import name_key
from scopesteps.sources.client import quote_key, quote_matches

USER_STORY = re.compile(r"^As an? .+?, I want .+", re.IGNORECASE | re.DOTALL)
MAX_REPORTED = 8


ProblemCode = Literal[
    "unknown_block",
    "quote_not_verbatim",
    "unasked_open_statement",
    "unasked_open_decision",
    "epic_has_criteria",
    "epic_without_criteria",
    "story_format",
    "story_without_criteria",
    "unused_reviewer_answer",
    "unaccounted_block",
    "uncovered_confirmed_statement",
    "covers_excluded_statement",
    "person_without_citation",
    "person_not_named",
    "stated_right_without_citation",
]
MISSING_QUESTION_CODES = frozenset({"unasked_open_statement", "unasked_open_decision"})
BASE_CHECKS: frozenset[ProblemCode] = frozenset(
    {
        "unknown_block",
        "quote_not_verbatim",
        "unasked_open_statement",
        "unasked_open_decision",
        "epic_has_criteria",
        "story_format",
        "story_without_criteria",
    }
)
_ADDED_FOR_TRACEABILITY: frozenset[ProblemCode] = frozenset(
    {
        "unused_reviewer_answer",
        "unaccounted_block",
        "uncovered_confirmed_statement",
        "covers_excluded_statement",
    }
)
TRACEABILITY_CHECKS: frozenset[ProblemCode] = BASE_CHECKS | _ADDED_FOR_TRACEABILITY
_ADDED_FOR_PEOPLE: frozenset[ProblemCode] = frozenset(
    {"person_without_citation", "person_not_named", "stated_right_without_citation"}
)
PEOPLE_CHECKS: frozenset[ProblemCode] = TRACEABILITY_CHECKS | _ADDED_FOR_PEOPLE
# From draft-v8 on, epics carry the outcomes that hold once their stories are done.
_REMOVED_FOR_DETAIL: frozenset[ProblemCode] = frozenset({"epic_has_criteria"})
_ADDED_FOR_DETAIL: frozenset[ProblemCode] = frozenset({"epic_without_criteria"})
DETAIL_CHECKS: frozenset[ProblemCode] = (PEOPLE_CHECKS - _REMOVED_FOR_DETAIL) | _ADDED_FOR_DETAIL


@dataclass(frozen=True)
class Problem:
    code: ProblemCode
    message: str
    blocks: tuple[str, ...] = ()
    """For missing questions: the blocks the question must cite."""


def find_problems(
    draft: AnyDraft,
    blocks: Sequence[SourceBlockInput],
    *,
    open_decision_blocks: Collection[str] = (),
    answer_blocks: Collection[str] = (),
    account_blocks: Collection[str] = (),
    enabled: Collection[ProblemCode] = TRACEABILITY_CHECKS,
    attribute_quotes: bool = False,
) -> list[Problem]:
    """Problems a reviewer would block on; empty when the draft passes.

    `open_decision_blocks` are blocks recording decisions known to be unresolved (for example a
    question the reviewer skipped). Each must be raised as a clarification question.
    `answer_blocks` are reviewer answers. Each is a confirmed decision and must be cited by at least
    one source-backed acceptance criterion, so its provenance is visible.
    `account_blocks` are source blocks that must each be cited by at least one statement, so no
    passage is silently skipped. Traceability checks need a draft-backlog.v2 draft, and the
    people checks a draft-backlog.v4 one.
    `enabled` selects the checks, so each prompt version keeps the check set it was measured with.
    `attribute_quotes` names the speakers attribute in the message for a quote taken from it, so
    the repair can fix it; earlier prompts keep the message they were measured with.
    """
    texts = {block.id: block.text for block in blocks}
    speakers = {block.id: block.speakers for block in blocks}
    problems: list[Problem] = []

    for owner, citation in _citations(draft):
        if citation.block_id not in texts:
            problems.append(
                Problem("unknown_block", f"{owner} cites unknown block {citation.block_id}")
            )
        elif not quote_matches(citation.quote, texts[citation.block_id]):
            shown = describe_speakers(speakers[citation.block_id])
            from_attribute = attribute_quotes and shown and quote_matches(citation.quote, shown)
            problems.append(
                Problem(
                    "quote_not_verbatim",
                    f"{owner} quote is from the speakers attribute of {citation.block_id}, not "
                    f"its text; quote only the text inside the tag: {citation.quote!r}"
                    if from_attribute
                    else f"{owner} quote is not verbatim from {citation.block_id}",
                )
            )

    asked = {cite.block_id for question in draft.questions for cite in question.citations}
    for statement in draft.statements:
        cited = tuple(sorted({cite.block_id for cite in statement.citations}))
        if statement.kind in {"conflict", "open_question"} and not set(cited) & asked:
            problems.append(
                Problem(
                    "unasked_open_statement",
                    f"{statement.kind} '{statement.summary[:60]}' has no clarification question "
                    f"citing {', '.join(cited)}",
                    cited,
                )
            )
    for block_id in sorted(open_decision_blocks):
        if block_id not in asked:
            problems.append(
                Problem(
                    "unasked_open_decision",
                    f"open decision {block_id} is unresolved and needs a question citing it",
                    (block_id,),
                )
            )

    sourced = {
        cite.block_id
        for item in draft.items
        for criterion in item.criteria
        if criterion.origin == "source"
        for cite in criterion.citations
    }
    for block_id in sorted(answer_blocks):
        if block_id not in sourced:
            problems.append(
                Problem(
                    "unused_reviewer_answer",
                    f"reviewer answer {block_id} is not cited by any acceptance criterion with "
                    "origin 'source'; add it to the story it affects",
                    (block_id,),
                )
            )

    if not isinstance(draft, DraftBacklogV1):
        problems += _traceability_problems(draft, account_blocks)
    if isinstance(draft, DraftBacklogV4):
        problems += _people_problems(draft, texts, speakers)

    for item in draft.items:
        if item.kind == "epic" and item.criteria:
            problems.append(
                Problem(
                    "epic_has_criteria",
                    f"epic {item.ref} has acceptance criteria; put them on its stories",
                )
            )
        if item.kind == "epic" and not item.criteria:
            problems.append(
                Problem(
                    "epic_without_criteria",
                    f"epic {item.ref} has no acceptance criteria; add the outcomes that hold "
                    "once its stories are done",
                )
            )
        if item.kind == "story" and not USER_STORY.match(item.description.strip()):
            problems.append(
                Problem(
                    "story_format",
                    f"story {item.ref} description is not 'As a <role>, I want ...'",
                )
            )
        if item.kind == "story" and not item.criteria:
            problems.append(
                Problem("story_without_criteria", f"story {item.ref} has no acceptance criteria")
            )
    return [problem for problem in problems if problem.code in enabled]


def check_draft(
    draft: AnyDraft,
    blocks: Sequence[SourceBlockInput],
    *,
    open_decision_blocks: Collection[str] = (),
    answer_blocks: Collection[str] = (),
    account_blocks: Collection[str] = (),
    enabled: Collection[ProblemCode] = TRACEABILITY_CHECKS,
    attribute_quotes: bool = False,
) -> list[str]:
    """Problem messages, capped for use in prompts and reports."""
    messages = [
        problem.message
        for problem in find_problems(
            draft,
            blocks,
            open_decision_blocks=open_decision_blocks,
            answer_blocks=answer_blocks,
            account_blocks=account_blocks,
            enabled=enabled,
            attribute_quotes=attribute_quotes,
        )
    ]
    return messages[:MAX_REPORTED] + (
        [f"and {len(messages) - MAX_REPORTED} more"] if len(messages) > MAX_REPORTED else []
    )


def requirement_blocks(
    blocks: Sequence[SourceBlockInput], *, exclude: Collection[str] = ()
) -> list[str]:
    """Source blocks a draft must account for: everything except headings and excluded ids."""
    return [
        block.id
        for block in blocks
        if block.id not in exclude and not block.text.lstrip().startswith("#")
    ]


def _traceability_problems(
    draft: DraftBacklog | DraftBacklogV3, account_blocks: Collection[str]
) -> list[Problem]:
    problems: list[Problem] = []
    stated = {cite.block_id for statement in draft.statements for cite in statement.citations}
    for block_id in account_blocks:
        if block_id not in stated:
            problems.append(
                Problem(
                    "unaccounted_block",
                    f"source {block_id} is not cited by any statement; classify it "
                    "(use kind 'context' if it holds no requirement or decision)",
                    (block_id,),
                )
            )
    kinds = {statement.id: statement.kind for statement in draft.statements}
    covered = {ref for item in draft.items if item.kind == "story" for ref in item.covers}
    for statement in draft.statements:
        if statement.kind == "confirmed" and statement.id not in covered:
            problems.append(
                Problem(
                    "uncovered_confirmed_statement",
                    f"confirmed statement {statement.id} '{statement.summary[:60]}' is not "
                    "covered by any story",
                )
            )
    for item in draft.items:
        for ref in item.covers:
            if kinds.get(ref) in {"exclusion", "proposal"}:
                problems.append(
                    Problem(
                        "covers_excluded_statement",
                        f"{item.ref} covers {kinds[ref]} statement {ref}; only confirmed scope "
                        "becomes stories",
                    )
                )
    return problems


def names(key: str, text: str, speakers: Sequence[SpeakerNote] = ()) -> bool:
    """Whether a block names the person whose name is `key` (`name_key` form): in its text, or
    as a speaker in it whom an editor confirmed under that name (ADR 0012)."""
    return key in name_key(quote_key(text)) or any(
        note.name is not None and name_key(note.name) == key for note in speakers
    )


def _people_problems(
    draft: DraftBacklogV4,
    texts: dict[str, str],
    speakers: dict[str, tuple[SpeakerNote, ...]],
) -> list[Problem]:
    """Every person is cited and named in a block they cite, so nobody is invented, and every
    stated decision right is cited, so a right is never inferred."""
    problems: list[Problem] = []
    for person in draft.people:
        if not person.citations:
            problems.append(
                Problem(
                    "person_without_citation",
                    f"person {person.ref} '{person.name[:60]}' has no citation; cite the block "
                    "that names them, or remove them",
                )
            )
        elif not any(
            names(
                name_key(person.name),
                texts.get(cite.block_id, ""),
                speakers.get(cite.block_id, ()),
            )
            for cite in person.citations
        ):
            problems.append(
                Problem(
                    "person_not_named",
                    f"person {person.ref} '{person.name[:60]}' is not named in any block they "
                    "cite; cite the block that names them and write the name as it is there",
                )
            )
        if person.rights != "not_stated" and not person.rights_citations:
            problems.append(
                Problem(
                    "stated_right_without_citation",
                    f"person {person.ref} has rights '{person.rights}' with no citation; cite "
                    "the block that states it, or set rights to 'not_stated'",
                )
            )
    return problems


def _citations(draft: AnyDraft) -> Iterator[tuple[str, Citation]]:
    for index, statement in enumerate(draft.statements):
        # v2 statements are named by id so a targeted repair can replace exactly that one.
        owner = (
            f"statement {statement.id}"
            if isinstance(statement, Statement)
            else f"statement {index + 1}"
        )
        for citation in statement.citations:
            yield owner, citation
    for item in draft.items:
        for criterion in item.criteria:
            for citation in criterion.citations:
                yield f"{item.ref} criterion", citation
    for index, question in enumerate(draft.questions):
        for citation in question.citations:
            yield f"question {index + 1}", citation
    if isinstance(draft, DraftBacklogV4):
        for person in draft.people:
            for citation in person.citations:
                yield f"person {person.ref}", citation
            for citation in person.rights_citations:
                yield f"person {person.ref} rights", citation
