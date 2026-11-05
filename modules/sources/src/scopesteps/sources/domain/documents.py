"""Text read out of Word, PDF and WebVTT files, and how it becomes a source's text and blocks.

A reader turns a file into passages. Each passage becomes exactly one block, so a page number or
a caption's time stays with the paragraph it belongs to (ADR 0025).
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from scopesteps.sources.domain.blocks import TextBlock, normalize_text, split_into_blocks
from scopesteps.sources.domain.speakers import is_turn_header, turn_start

# A caption is a few words. Captions are joined into one paragraph per turn, but a long monologue
# is split near this length so a citation points at a passage a reader can find.
MAX_TURN_CHARS = 1000

_BLANK_LINES = re.compile(r"\n(?:[ \t]*\n)+")
_SPACES = re.compile(r"[ \t\u00a0]+")
# Extracted text can carry control characters a file uses for layout; they are not text, and
# Postgres cannot store NUL.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class Rejection(StrEnum):
    """Why a reader refused a file. Each becomes its own error code for the person uploading."""

    WRONG_TYPE = "wrong_type"
    PASSWORD_PROTECTED = "password_protected"  # noqa: S105 - a reason, not a password
    NO_TEXT = "no_text"
    DAMAGED = "damaged"
    TOO_LARGE_UNPACKED = "too_large_unpacked"


class DocumentRejectedError(Exception):
    """Raised by a reader. The use case turns it into an error that names the file."""

    def __init__(self, reason: Rejection) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True)
class Passage:
    """One paragraph of a converted file, with where it is in the file when the file says."""

    text: str
    page: int | None = None
    start_ms: int | None = None
    speaker: str | None = None


def clean_line(line: str) -> str:
    """One line of extracted text with runs of spaces collapsed, as PDF layout pads them."""
    return _SPACES.sub(" ", line).strip()


def assemble(passages: Iterable[Passage]) -> tuple[str, list[TextBlock]]:
    """The stored text and its blocks: passages joined by blank lines, one block each.

    A blank line inside a passage would split it into two blocks, so it is removed, as are control
    characters. Empty passages are dropped.
    """
    kept: list[Passage] = []
    for passage in passages:
        plain = _CONTROL_CHARACTERS.sub("", normalize_text(passage.text))
        lines = [line.rstrip() for line in plain.split("\n")]
        text = _BLANK_LINES.sub("\n", "\n".join(lines)).strip()
        if text:
            kept.append(replace(passage, text=text))
    text = "\n\n".join(passage.text for passage in kept)
    blocks = split_into_blocks(text)
    # Holds by construction: every passage is non-empty and has no blank line.
    if len(blocks) != len(kept):  # pragma: no cover
        raise AssertionError("each passage must become exactly one block")
    return text, [
        replace(block, page=passage.page, start_ms=passage.start_ms, speaker=passage.speaker)
        for block, passage in zip(blocks, kept, strict=True)
    ]


def caption_turns(captions: Sequence[Passage]) -> list[Passage]:
    """WebVTT captions as one paragraph per turn: "Dana Ruiz: what was said".

    Consecutive captions by one speaker (`speaker` is the caption's voice tag) are joined, up to
    `MAX_TURN_CHARS`, and the paragraph keeps the first caption's time. Captions without a voice
    tag are joined the same way, so a speaker written in the text ("Dana: ...") stays readable.
    """
    turns: list[Passage] = []
    words: list[str] = []
    current: Passage | None = None

    def close() -> None:
        if current is not None and words:
            said = " ".join(words)
            text = f"{current.speaker}: {said}" if current.speaker else said
            turns.append(Passage(text=text, start_ms=current.start_ms))

    for caption in captions:
        said = " ".join(clean_line(line) for line in caption.text.split("\n") if line.strip())
        if not said:
            continue
        same_turn = current is not None and current.speaker == caption.speaker
        if not same_turn or sum(len(word) + 1 for word in words) + len(said) > MAX_TURN_CHARS:
            close()
            current, words = caption, []
        words.append(said)
    close()
    return turns


def join_turn_headers(passages: Sequence[Passage]) -> list[Passage]:
    """Puts a paragraph that is only a speaker header ("Dana Ruiz   0:03") with the turn after it.

    Word transcripts from Teams keep the header and the words in separate paragraphs; together
    they read as one turn, as in a text transcript.
    """
    joined: list[Passage] = []
    pending: list[str] = []
    for passage in passages:
        if is_turn_header(passage.text):
            pending.append(passage.text)
            continue
        joined.append(replace(passage, text="\n".join([*pending, passage.text])))
        pending = []
    if pending:
        joined.append(Passage(text="\n".join(pending)))
    return joined


def mark_turns(blocks: Sequence[TextBlock]) -> list[TextBlock]:
    """Transcript blocks with the speaker and time their first lines name (ADR 0012's formats).

    A time the file gave (a caption's) is kept; the speaker always comes from the text, so it is
    the same label speaker detection finds.
    """
    marked: list[TextBlock] = []
    for block in blocks:
        start = turn_start(block.text)
        start_ms = block.start_ms if block.start_ms is not None else start.start_ms
        marked.append(replace(block, start_ms=start_ms, speaker=start.speaker))
    return marked
