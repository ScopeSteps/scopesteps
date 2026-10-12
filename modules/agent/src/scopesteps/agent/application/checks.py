"""Deterministic checks on a schema-valid draft. Prompts are not relied on for these guarantees.

They feed the repair attempt during drafting and later back the agent's `validate_backlog` tool,
so the single-pass baseline and the agent are held to the same rules.
"""

import re
from collections.abc import Collection, Iterator, Sequence

from scopesteps.agent.application.schemas import Citation, DraftBacklog, SourceBlockInput
from scopesteps.sources.client import quote_matches

USER_STORY = re.compile(r"^As an? .+?, I want .+", re.IGNORECASE | re.DOTALL)
MAX_REPORTED = 8


def check_draft(
    draft: DraftBacklog,
    blocks: Sequence[SourceBlockInput],
    *,
    open_decision_blocks: Collection[str] = (),
) -> list[str]:
    """Return problems a reviewer would block on; empty when the draft passes.

    `open_decision_blocks` are blocks recording decisions known to be unresolved (for example a
    question the reviewer skipped). Each must be raised as a clarification question.
    """
    texts = {block.id: block.text for block in blocks}
    problems: list[str] = []

    for owner, citation in _citations(draft):
        if citation.block_id not in texts:
            problems.append(f"{owner} cites unknown block {citation.block_id}")
        elif not quote_matches(citation.quote, texts[citation.block_id]):
            problems.append(f"{owner} quote is not verbatim from {citation.block_id}")

    asked = {cite.block_id for question in draft.questions for cite in question.citations}
    for statement in draft.statements:
        cited = {cite.block_id for cite in statement.citations}
        if statement.kind in {"conflict", "open_question"} and not cited & asked:
            problems.append(
                f"{statement.kind} '{statement.summary[:60]}' has no clarification question "
                f"citing {', '.join(sorted(cited))}"
            )
    for block_id in sorted(open_decision_blocks):
        if block_id not in asked:
            problems.append(
                f"open decision {block_id} is unresolved and needs a question citing it"
            )

    for item in draft.items:
        if item.kind == "epic" and item.criteria:
            problems.append(f"epic {item.ref} has acceptance criteria; put them on its stories")
        if item.kind == "story" and not USER_STORY.match(item.description.strip()):
            problems.append(f"story {item.ref} description is not 'As a <role>, I want ...'")
        if item.kind == "story" and not item.criteria:
            problems.append(f"story {item.ref} has no acceptance criteria")
    return problems[:MAX_REPORTED] + (
        [f"and {len(problems) - MAX_REPORTED} more"] if len(problems) > MAX_REPORTED else []
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
