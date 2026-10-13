"""Citation validation: a reference is usable only if it resolves to an exact stored passage of
the project. It says nothing about whether the passage supports the claim; people judge that."""

from collections.abc import Collection, Iterable, Mapping
from uuid import UUID

from scopesteps.evidence.domain.citation import Citation, InvalidCitation
from scopesteps.sources.client import SourcePassage, quote_matches


def find_invalid_citations(
    citations: Iterable[Citation],
    passages: Mapping[UUID, SourcePassage],
    project_versions: Collection[UUID],
) -> list[InvalidCitation]:
    """`passages` are the project's paragraphs by block id; `project_versions` the cited versions
    that belong to the project."""
    invalid: list[InvalidCitation] = []
    for citation in citations:
        passage = passages.get(citation.block_id)
        if citation.source_version_id not in project_versions:
            invalid.append(InvalidCitation(citation, "source_version_not_in_project"))
        elif passage is None or passage.source_version_id != citation.source_version_id:
            invalid.append(InvalidCitation(citation, "unknown_block"))
        elif citation.quote is not None and not quote_matches(citation.quote, passage.text):
            invalid.append(InvalidCitation(citation, "quote_not_found"))
    return invalid
