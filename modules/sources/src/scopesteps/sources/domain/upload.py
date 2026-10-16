"""Validation of uploaded files. Uploaded text is stored and shown as data, never interpreted."""

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from scopesteps.sources.domain.blocks import TextBlock, normalize_text, split_into_blocks
from scopesteps.sources.domain.errors import (
    EmptySourceError,
    SourceTooLargeError,
    SourceWordLimitError,
    UnreadableSourceError,
    UnsupportedSourceTypeError,
)
from scopesteps.sources.domain.source import MediaType, SourceKind

MEDIA_TYPE_BY_SUFFIX = {
    ".txt": MediaType.PLAIN_TEXT,
    ".md": MediaType.MARKDOWN,
    ".markdown": MediaType.MARKDOWN,
}
MAX_FILENAME_LENGTH = 255

_PATH_SEPARATORS = re.compile(r"[/\\]")
# Tab, line feed, form feed and carriage return are ordinary in text files; any other control
# character means the file is binary or damaged.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class SourceLimits:
    max_bytes: int
    max_words: int


@dataclass(frozen=True)
class UploadedFile:
    """A file as the client sent it. The filename is untrusted and `content` is unvalidated."""

    kind: SourceKind
    filename: str
    content: bytes


@dataclass(frozen=True)
class ParsedSource:
    kind: SourceKind
    filename: str
    media_type: MediaType
    checksum_sha256: str
    byte_size: int
    text: str
    word_count: int
    blocks: tuple[TextBlock, ...]


def display_filename(raw: str) -> str:
    """Reduce a client filename to display metadata: no directories, no control characters."""
    name = _PATH_SEPARATORS.split(raw)[-1]
    name = "".join(character for character in name if character.isprintable()).strip()
    suffix = PurePosixPath(name).suffix
    if len(name) > MAX_FILENAME_LENGTH and len(suffix) < MAX_FILENAME_LENGTH:
        name = name[: MAX_FILENAME_LENGTH - len(suffix)] + suffix
    return name[:MAX_FILENAME_LENGTH]


def request_fingerprint(files: Sequence[UploadedFile], target: str = "") -> str:
    """Identifies an upload command's content, to tell a retry from a reused idempotency key.

    `target` names the source a new version is for; an upload of new sources has none.
    """
    parts = [
        [file.kind.value, file.filename, hashlib.sha256(file.content).hexdigest()] for file in files
    ]
    payload: object = {"target": target, "files": parts} if target else parts
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def parse_text(kind: SourceKind, filename: str, text: str) -> ParsedSource:
    """Text the application already holds (a change request), stored like an uploaded file."""
    content = text.encode()
    normalized = normalize_text(text)
    blocks = split_into_blocks(normalized)
    if not blocks:
        raise EmptySourceError("The text is empty")
    return ParsedSource(
        kind=kind,
        filename=filename,
        media_type=MediaType.PLAIN_TEXT,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
        text=normalized,
        word_count=len(normalized.split()),
        blocks=tuple(blocks),
    )


def parse_uploads(files: Sequence[UploadedFile], limits: SourceLimits) -> list[ParsedSource]:
    """Validate every file on its own; raises on the first problem. See `check_word_limit`."""
    return [_parse_upload(file, limits) for file in files]


def check_word_limit(current_words: int, added_words: int, limits: SourceLimits) -> None:
    """The limit covers the project's current sources together, not each upload alone."""
    total_words = current_words + added_words
    if total_words > limits.max_words:
        raise SourceWordLimitError(
            f"The project's sources would contain {total_words:,} words in total; the limit is "
            f"{limits.max_words:,}. Remove a source or shorten the file, then upload again.",
            details={
                "word_count": total_words,
                "current_word_count": current_words,
                "max_words": limits.max_words,
            },
        )


def _parse_upload(file: UploadedFile, limits: SourceLimits) -> ParsedSource:
    filename = display_filename(file.filename)
    details: dict[str, object] = {"field": file.kind.value, "filename": filename}
    label = filename or f"The {file.kind.label}"

    # The file's name decides its type: a client-declared Content-Type is as untrusted as the
    # name and browsers disagree on what they send for Markdown.
    media_type = MEDIA_TYPE_BY_SUFFIX.get(PurePosixPath(filename).suffix.lower())
    if media_type is None:
        raise UnsupportedSourceTypeError(
            f"{label} must be a .txt or .md file", details={**details, "supported": [".txt", ".md"]}
        )
    if len(file.content) > limits.max_bytes:
        raise SourceTooLargeError(
            f"{label} is larger than the {limits.max_bytes // 1024} KiB limit",
            details={**details, "max_bytes": limits.max_bytes},
        )
    try:
        decoded = file.content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise UnreadableSourceError(
            f"{label} is not UTF-8 text. Save it as UTF-8 and upload again.", details=details
        ) from error
    if _CONTROL_CHARACTERS.search(decoded):
        raise UnreadableSourceError(
            f"{label} contains binary data. Upload a plain text or Markdown file.", details=details
        )

    text = normalize_text(decoded)
    blocks = split_into_blocks(text)
    if not blocks:
        raise EmptySourceError(
            f"{label} has no text. Add some text to it and upload again.", details=details
        )
    return ParsedSource(
        kind=file.kind,
        filename=filename,
        media_type=media_type,
        checksum_sha256=hashlib.sha256(file.content).hexdigest(),
        byte_size=len(file.content),
        text=text,
        word_count=len(text.split()),
        blocks=tuple(blocks),
    )
