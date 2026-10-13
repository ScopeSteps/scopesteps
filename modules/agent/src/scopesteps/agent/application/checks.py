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
    SourceBlockInput,
    Statement,
)
from scopesteps.sources.client import quote_matches

USER_STORY = re.compile(r"^As an? .+?, I want .+", re.IGNORECASE | re.DOTALL)
MAX_REPORTED = 8


ProblemCode = Literal[
    "unknown_block",
    "quote_not_verbatim",
    "unasked_open_statement",
    "unasked_open_decision",
    "epic_has_criteria",
    "story_format",
    "story_without_criteria",
    "unused_reviewer_answer",
    "unaccounted_block",
    "uncovered_confirmed_statement",
    "covers_excluded_statement",
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
) -> list[Problem]:
    """Problems a reviewer would block on; empty when the draft passes.

    `open_decision_blocks` are blocks recording decisions known to be unresolved (for example a
    question the reviewer skipped). Each must be raised as a clarification question.
    `answer_blocks` are reviewer answers. Each is a confirmed decision and must be cited by at least
    one source-backed acceptance criterion, so its provenance is visible.
    `account_blocks` are source blocks that must each be cited by at least one statement, so no
    passage is silently skipped. Traceability checks need a draft-backlog.v2 draft.
    `enabled` selects the checks, so each prompt version keeps the check set it was measured with.
    """
    texts = {block.id: block.text for block in blocks}
    problems: list[Problem] = []

    for owner, citation in _citations(draft):
        if citation.block_id not in texts:
            problems.append(
                Problem("unknown_block", f"{owner} cites unknown block {citation.block_id}")
            )
        elif not quote_matches(citation.quote, texts[citation.block_id]):
            problems.append(
                Problem(
                    "quote_not_verbatim",
                    f"{owner} quote is not verbatim from {citation.block_id}",
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

    if isinstance(draft, DraftBacklog):
        problems += _traceability_problems(draft, account_blocks)

    for item in draft.items:
        if item.kind == "epic" and item.criteria:
            problems.append(
                Problem(
                    "epic_has_criteria",
                    f"epic {item.ref} has acceptance criteria; put them on its stories",
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


def _traceability_problems(draft: DraftBacklog, account_blocks: Collection[str]) -> list[Problem]:
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
