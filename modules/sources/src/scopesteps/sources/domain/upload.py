"""Validation of uploaded files. Uploaded text is stored and shown as data, never interpreted.

Text files are stored as sent. Word, PDF and WebVTT files are read into passages first by a
reader outside the domain (ADR 0025); `parse_passages` turns those into the same text and blocks.
"""

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from scopesteps.kernel.errors import DomainError
from scopesteps.sources.domain.blocks import TextBlock, normalize_text, split_into_blocks
from scopesteps.sources.domain.documents import (
    Passage,
    Rejection,
    assemble,
    caption_turns,
    join_turn_headers,
    mark_turns,
)
from scopesteps.sources.domain.errors import (
    EmptySourceError,
    ScannedSourceError,
    SourcePasswordProtectedError,
    SourceTooLargeError,
    SourceTooLargeUnpackedError,
    SourceTypeMismatchError,
    SourceWordLimitError,
    UnreadableSourceError,
    UnsupportedSourceTypeError,
)
from scopesteps.sources.domain.source import MediaType, SourceKind

MEDIA_TYPE_BY_SUFFIX = {
    ".txt": MediaType.PLAIN_TEXT,
    ".md": MediaType.MARKDOWN,
    ".markdown": MediaType.MARKDOWN,
    ".docx": MediaType.WORD,
    ".pdf": MediaType.PDF,
    ".vtt": MediaType.WEBVTT,
}
SUPPORTED_SUFFIXES = (".txt", ".md", ".docx", ".pdf", ".vtt")
_FORMAT_NAMES = {
    MediaType.PLAIN_TEXT: "text",
    MediaType.MARKDOWN: "Markdown",
    MediaType.WORD: "Word (.docx)",
    MediaType.PDF: "PDF",
    MediaType.WEBVTT: "WebVTT transcript (.vtt)",
}
MAX_FILENAME_LENGTH = 255

_PATH_SEPARATORS = re.compile(r"[/\\]")
# Tab, line feed, form feed and carriage return are ordinary in text files; any other control
# character means the file is binary or damaged.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class SourceLimits:
    """`max_bytes` is per text file; `max_document_bytes` per Word, PDF or WebVTT file, which
    carry layout, images or timings beside their words. The word limit is what bounds the text."""

    max_bytes: int
    max_words: int
    max_document_bytes: int

    def max_bytes_for(self, media_type: MediaType) -> int:
        return self.max_bytes if media_type.is_text else self.max_document_bytes

    @property
    def largest_file_bytes(self) -> int:
        return max(self.max_bytes, self.max_document_bytes)


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


@dataclass(frozen=True)
class CheckedUpload:
    """A file whose name gives a supported type and whose size is within that type's limit."""

    file: UploadedFile
    filename: str
    media_type: MediaType

    @property
    def details(self) -> dict[str, object]:
        return {"field": self.file.kind.value, "filename": self.filename}

    @property
    def label(self) -> str:
        return self.filename or f"The {self.file.kind.label}"


def check_upload(file: UploadedFile, limits: SourceLimits) -> CheckedUpload:
    """The file's name decides its type: a client-declared Content-Type is as untrusted as the
    name, and browsers disagree on what they send for Markdown. A reader then checks that the
    content really is that type."""
    filename = display_filename(file.filename)
    details: dict[str, object] = {"field": file.kind.value, "filename": filename}
    label = filename or f"The {file.kind.label}"
    media_type = MEDIA_TYPE_BY_SUFFIX.get(PurePosixPath(filename).suffix.lower())
    if media_type is None:
        raise UnsupportedSourceTypeError(
            f"{label} must be a .txt, .md, .docx, .pdf or .vtt file",
            details={**details, "supported": list(SUPPORTED_SUFFIXES)},
        )
    max_bytes = limits.max_bytes_for(media_type)
    if len(file.content) > max_bytes:
        raise SourceTooLargeError(
            f"{label} is larger than the {_size(max_bytes)} limit",
            details={**details, "max_bytes": max_bytes},
        )
    return CheckedUpload(file=file, filename=filename, media_type=media_type)


def parse_plain_text(upload: CheckedUpload) -> ParsedSource:
    """A .txt or .md file, stored as sent once line endings are normalized."""
    label, details = upload.label, upload.details
    try:
        decoded = upload.file.content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise UnreadableSourceError(
            f"{label} is not UTF-8 text. Save it as UTF-8 and upload again.", details=details
        ) from error
    if _CONTROL_CHARACTERS.search(decoded):
        raise UnreadableSourceError(
            f"{label} contains binary data. Upload a plain text or Markdown file.", details=details
        )
    text = normalize_text(decoded)
    return _parsed(upload, text, split_into_blocks(text))


def parse_passages(upload: CheckedUpload, passages: Sequence[Passage]) -> ParsedSource:
    """A converted file's passages as text and blocks, one block per passage.

    WebVTT captions are joined into turns, and a Word transcript's header paragraphs are put
    with the turn after them, so a transcript reads the same whichever format it came in.
    """
    if upload.media_type is MediaType.WEBVTT:
        passages = caption_turns(passages)
    elif upload.file.kind is SourceKind.TRANSCRIPT:
        passages = join_turn_headers(passages)
    text, blocks = assemble(passages)
    return _parsed(upload, text, blocks)


def rejection_error(upload: CheckedUpload, reason: Rejection) -> DomainError:
    """The error a reader's refusal becomes, in plain words that name the file."""
    label, details = upload.label, upload.details
    format_name = _FORMAT_NAMES[upload.media_type]
    match reason:
        case Rejection.WRONG_TYPE:
            return SourceTypeMismatchError(
                f"{label} is not really a {format_name} file. Open it, save it as "
                f"{format_name} and upload it again.",
                details=details,
            )
        case Rejection.PASSWORD_PROTECTED:
            return SourcePasswordProtectedError(
                f"{label} is protected by a password. Remove the password and upload it again.",
                details=details,
            )
        case Rejection.NO_TEXT:
            return ScannedSourceError(
                f"{label} has no text to read: it looks like scanned pages. Upload a PDF with "
                "selectable text, or a Word file.",
                details=details,
            )
        case Rejection.TOO_LARGE_UNPACKED:
            return SourceTooLargeUnpackedError(
                f"{label} is too large once opened. Split it into smaller files and upload them.",
                details=details,
            )
        case Rejection.DAMAGED:
            return UnreadableSourceError(
                f"{label} is damaged or cannot be read. Open it, save it again and upload it.",
                details=details,
            )


def _parsed(upload: CheckedUpload, text: str, blocks: Sequence[TextBlock]) -> ParsedSource:
    if not blocks:
        raise EmptySourceError(
            f"{upload.label} has no text. Add some text to it and upload again.",
            details=upload.details,
        )
    if upload.file.kind is SourceKind.TRANSCRIPT:
        blocks = mark_turns(blocks)
    return ParsedSource(
        kind=upload.file.kind,
        filename=upload.filename,
        media_type=upload.media_type,
        checksum_sha256=hashlib.sha256(upload.file.content).hexdigest(),
        byte_size=len(upload.file.content),
        text=text,
        word_count=len(text.split()),
        blocks=tuple(blocks),
    )


def _size(max_bytes: int) -> str:
    mib = 1024 * 1024
    if max_bytes >= mib and max_bytes % mib == 0:
        return f"{max_bytes // mib} MiB"
    return f"{max_bytes // 1024} KiB"
