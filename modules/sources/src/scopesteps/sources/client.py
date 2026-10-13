from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from scopesteps.projects.client import ProjectId
from scopesteps.sources.application.reading import versions_with_blocks
from scopesteps.sources.domain.blocks import (
    TextBlock,
    normalize_text,
    quote_key,
    quote_matches,
    split_into_blocks,
)
from scopesteps.sources.domain.ids import SourceBlockId, SourceId, SourceVersionId
from scopesteps.sources.infrastructure.repository import SqlSourceRepository


@dataclass(frozen=True)
class SourcePassage:
    """A stored paragraph as other modules see it. Versions are immutable, so callers may pin them."""

    block_id: SourceBlockId
    source_version_id: SourceVersionId
    source_kind: str
    filename: str
    ordinal: int
    text: str


def load_passages(
    session: Session, project_id: ProjectId, version_ids: Sequence[SourceVersionId]
) -> list[SourcePassage]:
    """Paragraphs of the given versions, version by version in the order given.

    Raises NotFoundError if a version does not belong to `project_id`. Callers check the actor's
    access to the project first.
    """
    return [
        SourcePassage(
            block_id=block.id,
            source_version_id=version.id,
            source_kind=version.kind.value,
            filename=version.filename,
            ordinal=block.ordinal,
            text=block.text,
        )
        for version, blocks in versions_with_blocks(
            SqlSourceRepository(session), project_id, version_ids
        )
        for block in blocks
    ]


__all__ = [
    "SourceBlockId",
    "SourceId",
    "SourcePassage",
    "SourceVersionId",
    "TextBlock",
    "load_passages",
    "normalize_text",
    "quote_key",
    "quote_matches",
    "split_into_blocks",
]
