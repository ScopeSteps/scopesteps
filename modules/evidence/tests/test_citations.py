from uuid import UUID

import pytest

from scopesteps.evidence.application.citations import find_invalid_citations
from scopesteps.evidence.domain.citation import Citation
from scopesteps.sources.client import SourceBlockId, SourcePassage, SourceVersionId

BRIEF, TRANSCRIPT, ELSEWHERE = UUID(int=1), UUID(int=2), UUID(int=3)
BLOCK, OTHER_BLOCK = UUID(int=11), UUID(int=12)
PASSAGES = {
    BLOCK: SourcePassage(
        block_id=SourceBlockId(BLOCK),
        source_version_id=SourceVersionId(BRIEF),
        source_kind="brief",
        filename="brief.md",
        ordinal=1,
        text="**Dana:** A booking can last up to 4 hours.",
    ),
    OTHER_BLOCK: SourcePassage(
        block_id=SourceBlockId(OTHER_BLOCK),
        source_version_id=SourceVersionId(TRANSCRIPT),
        source_kind="transcript",
        filename="transcript.md",
        ordinal=1,
        text="Three hours is the most I want.",
    ),
}


@pytest.mark.parametrize(
    ("citation", "fault"),
    [
        (Citation(BRIEF, BLOCK, "up to 4 hours"), None),
        (Citation(BRIEF, BLOCK, "Dana: A booking can last"), None),
        (Citation(BRIEF, BLOCK), None),
        (Citation(BRIEF, BLOCK, "up to 5 hours"), "quote_not_found"),
        (Citation(BRIEF, UUID(int=99), "up to 4 hours"), "unknown_block"),
        # A real block, cited under a version it does not belong to.
        (Citation(BRIEF, OTHER_BLOCK, "Three hours"), "unknown_block"),
        (Citation(ELSEWHERE, BLOCK, "up to 4 hours"), "source_version_not_in_project"),
    ],
)
def test_a_citation_is_valid_only_if_it_resolves_to_the_exact_stored_passage(
    citation: Citation, fault: str | None
) -> None:
    invalid = find_invalid_citations([citation], PASSAGES, {BRIEF, TRANSCRIPT})

    assert [found.fault for found in invalid] == ([fault] if fault else [])
    assert all(
        str(citation.block_id) in found.message or "version" in found.message for found in invalid
    )
