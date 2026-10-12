import re
from dataclasses import dataclass

_BLANK_LINES = re.compile(r"\n[ \t]*\n")


@dataclass(frozen=True)
class TextBlock:
    """A citable paragraph. Offsets index into the normalized text (LF line endings)."""

    ordinal: int
    text: str
    start_offset: int
    end_offset: int


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_into_blocks(text: str) -> list[TextBlock]:
    """Split on blank lines. Ordinals start at 1 and are the paragraph numbers cited as evidence.

    Fixtures and stored source blocks must use this rule, or citations point at the wrong passage.
    """
    normalized = normalize_text(text)
    blocks: list[TextBlock] = []
    start = 0
    for separator in [*_BLANK_LINES.finditer(normalized), None]:
        end = separator.start() if separator else len(normalized)
        chunk = normalized[start:end]
        stripped = chunk.strip()
        if stripped:
            leading = len(chunk) - len(chunk.lstrip())
            block_start = start + leading
            blocks.append(
                TextBlock(
                    ordinal=len(blocks) + 1,
                    text=stripped,
                    start_offset=block_start,
                    end_offset=block_start + len(stripped),
                )
            )
        if separator:
            start = separator.end()
    return blocks
