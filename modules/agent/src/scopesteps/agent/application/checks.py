"""Deterministic checks on a schema-valid draft. Prompts are not relied on for these guarantees.

They feed the repair attempt during drafting and later back the agent's `validate_backlog` tool,
so the single-pass baseline and the agent are held to the same rules.
"""

import re
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from scopesteps.agent.application.schemas import Citation, DraftBacklog, SourceBlockInput
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
]
MISSING_QUESTION_CODES = frozenset({"unasked_open_statement", "unasked_open_decision"})


@dataclass(frozen=True)
class Problem:
    code: ProblemCode
    message: str
    blocks: tuple[str, ...] = ()
    """For missing questions: the blocks the question must cite."""


def find_problems(
    draft: DraftBacklog,
    blocks: Sequence[SourceBlockInput],
    *,
    open_decision_blocks: Collection[str] = (),
) -> list[Problem]:
    """Problems a reviewer would block on; empty when the draft passes.

    `open_decision_blocks` are blocks recording decisions known to be unresolved (for example a
    question the reviewer skipped). Each must be raised as a clarification question.
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
    return problems


def check_draft(
    draft: DraftBacklog,
    blocks: Sequence[SourceBlockInput],
    *,
    open_decision_blocks: Collection[str] = (),
) -> list[str]:
    """Problem messages, capped for use in prompts and reports."""
    messages = [
        problem.message
        for problem in find_problems(draft, blocks, open_decision_blocks=open_decision_blocks)
    ]
    return messages[:MAX_REPORTED] + (
        [f"and {len(messages) - MAX_REPORTED} more"] if len(messages) > MAX_REPORTED else []
    )


def _citations(draft: DraftBacklog) -> Iterator[tuple[str, Citation]]:
    for index, statement in enumerate(draft.statements):
        for citation in statement.citations:
            yield f"statement {index + 1}", citation
    for item in draft.items:
        for criterion in item.criteria:
            for citation in criterion.citations:
                yield f"{item.ref} criterion", citation
    for index, question in enumerate(draft.questions):
        for citation in question.citations:
            yield f"question {index + 1}", citation
