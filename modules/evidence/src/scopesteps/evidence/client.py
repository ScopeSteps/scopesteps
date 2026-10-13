from collections.abc import Sequence
from typing import Literal, NewType
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from scopesteps.evidence.application.citations import find_invalid_citations
from scopesteps.evidence.domain.citation import Citation, CitationFault, InvalidCitation
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import (
    SourceBlockId,
    SourcePassage,
    SourceVersionId,
    load_passages,
)

EvidenceLinkId = NewType("EvidenceLinkId", UUID)


class EvidenceRef(BaseModel):
    """A pointer from a claim to the exact source passage that supports or contradicts it."""

    source_version_id: SourceVersionId
    block_id: SourceBlockId
    quote: str | None = Field(
        default=None, min_length=1, description="Verbatim text; null cites the whole paragraph."
    )
    relationship: Literal["supporting", "conflicting"] = "supporting"


def check_citations(
    session: Session, project_id: ProjectId, citations: Sequence[Citation]
) -> list[InvalidCitation]:
    """The citations that do not resolve to a stored passage of `project_id`.

    A source version of another project is reported exactly like one that does not exist.
    """
    passages: dict[UUID, SourcePassage] = {}
    project_versions: set[UUID] = set()
    for version_id in {citation.source_version_id for citation in citations}:
        try:
            loaded = load_passages(session, project_id, [SourceVersionId(version_id)])
        except NotFoundError:
            continue
        project_versions.add(version_id)
        passages |= {passage.block_id: passage for passage in loaded}
    return find_invalid_citations(citations, passages, project_versions)


__all__ = [
    "Citation",
    "CitationFault",
    "EvidenceLinkId",
    "EvidenceRef",
    "InvalidCitation",
    "check_citations",
]
