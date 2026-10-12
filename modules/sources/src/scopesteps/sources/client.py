from typing import NewType
from uuid import UUID

from scopesteps.sources.domain.blocks import (
    TextBlock,
    normalize_text,
    quote_key,
    quote_matches,
    split_into_blocks,
)

SourceId = NewType("SourceId", UUID)
SourceVersionId = NewType("SourceVersionId", UUID)
SourceBlockId = NewType("SourceBlockId", UUID)

__all__ = [
    "SourceBlockId",
    "SourceId",
    "SourceVersionId",
    "TextBlock",
    "normalize_text",
    "quote_key",
    "quote_matches",
    "split_into_blocks",
]
