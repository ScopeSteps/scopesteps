from dataclasses import dataclass
from typing import Literal
from uuid import UUID

CitationFault = Literal["source_version_not_in_project", "unknown_block", "quote_not_found"]


@dataclass(frozen=True)
class Citation:
    """A claim's pointer to a stored paragraph. `quote` is None when it cites the whole paragraph."""

    source_version_id: UUID
    block_id: UUID
    quote: str | None = None


@dataclass(frozen=True)
class InvalidCitation:
    citation: Citation
    fault: CitationFault

    @property
    def message(self) -> str:
        match self.fault:
            case "source_version_not_in_project":
                return f"source version {self.citation.source_version_id} is not in this project"
            case "unknown_block":
                return (
                    f"block {self.citation.block_id} is not a paragraph of source version "
                    f"{self.citation.source_version_id}"
                )
            case "quote_not_found":
                return f"the quote is not in block {self.citation.block_id}"
