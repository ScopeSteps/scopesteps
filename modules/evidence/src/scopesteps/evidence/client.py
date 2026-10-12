from typing import Literal, NewType
from uuid import UUID

from pydantic import BaseModel, Field

from scopesteps.sources.client import SourceBlockId, SourceVersionId

EvidenceLinkId = NewType("EvidenceLinkId", UUID)


class EvidenceRef(BaseModel):
    """A pointer from a claim to the exact source passage that supports or contradicts it."""

    source_version_id: SourceVersionId
    block_id: SourceBlockId
    quote: str = Field(min_length=1)
    relationship: Literal["supporting", "conflicting"] = "supporting"
