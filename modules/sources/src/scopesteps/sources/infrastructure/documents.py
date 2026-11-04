"""Readers that turn Word, PDF and WebVTT files into passages (ADR 0025).

Uploaded files are untrusted. Each reader first checks the file really is its format, uses a
well-known library in-process with no network access, never runs anything inside the file
(macros, scripts, links) and bounds what it unpacks before the library reads it.
"""

import html
import io
import re
import zipfile
from collections.abc import Iterable, Sequence
from typing import Protocol, cast

import docx
import webvtt
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PageObject, PasswordType, PdfReader
from pypdf.errors import LimitReachedError

from scopesteps.sources.application.upload import DocumentReaders
from scopesteps.sources.domain.documents import (
    DocumentRejectedError,
    Passage,
    Rejection,
    clean_line,
)
from scopesteps.sources.domain.source import MediaType

# A Word file is a zip archive of XML parts. python-docx reads every part into memory, so the
# archive's declared sizes are checked first: zipfile never reads past an entry's declared size,
# so they bound what opening it can cost. Real documents with images stay far below these.
MAX_WORD_PARTS = 1000
MAX_WORD_UNPACKED_BYTES = 64 * 1024 * 1024
# Text extraction time grows with pages. The word limit allows far fewer pages of text.
MAX_PDF_PAGES = 500

_ZIP_SIGNATURE = b"PK\x03\x04"
# Office saves a password-protected .docx as an OLE compound file holding an encrypted package;
# an old binary .doc is an OLE file too, without one.
_OLE_SIGNATURE = bytes.fromhex("d0cf11e0a1b11ae1")
_ENCRYPTED_PACKAGE = "EncryptedPackage".encode("utf-16-le")
_WORD_MAIN_PART = (
    b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
_CONTENT_TYPES = "[Content_Types].xml"
# PDF readers accept the header anywhere in the first kilobyte.
_PDF_HEADER_WINDOW = 1024
_BLANK_LINES = re.compile(r"\n\s*\n")
_CUE_TIME = re.compile(r"^(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})$")
_ZIP_ENCRYPTED_FLAG = 0x1


class WordReader:
    """Paragraphs and tables of the main document, in order, one passage each. Headers, footers,
    comments, footnotes and text boxes are left out. A table is one passage, a line per row."""

    def read(self, content: bytes) -> Sequence[Passage]:
        if content.startswith(_OLE_SIGNATURE):
            protected = _ENCRYPTED_PACKAGE in content
            raise DocumentRejectedError(
                Rejection.PASSWORD_PROTECTED if protected else Rejection.WRONG_TYPE
            )
        if not content.startswith(_ZIP_SIGNATURE):
            raise DocumentRejectedError(Rejection.WRONG_TYPE)
        _check_word_archive(content)
        try:
            document = docx.Document(io.BytesIO(content))
            return [_word_passage(item) for item in document.iter_inner_content()]
        # The library raises many kinds of error on damaged input (zip, XML, missing parts).
        except Exception as error:
            raise DocumentRejectedError(Rejection.DAMAGED) from error


def _check_word_archive(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            parts = archive.infolist()
            if any(part.flag_bits & _ZIP_ENCRYPTED_FLAG for part in parts):
                raise DocumentRejectedError(Rejection.PASSWORD_PROTECTED)
            if (
                len(parts) > MAX_WORD_PARTS
                or sum(part.file_size for part in parts) > MAX_WORD_UNPACKED_BYTES
            ):
                raise DocumentRejectedError(Rejection.TOO_LARGE_UNPACKED)
            if _CONTENT_TYPES not in archive.namelist():
                raise DocumentRejectedError(Rejection.WRONG_TYPE)
            content_types = archive.read(_CONTENT_TYPES)
    except zipfile.BadZipFile as error:
        raise DocumentRejectedError(Rejection.DAMAGED) from error
    # A macro-enabled document (.docm) or a template declares another main part type.
    if _WORD_MAIN_PART not in content_types:
        raise DocumentRejectedError(Rejection.WRONG_TYPE)


def _word_passage(item: Paragraph | Table) -> Passage:
    if isinstance(item, Paragraph):
        return Passage(text=item.text)
    rows: list[str] = []
    for row in item.rows:
        cells: list[str] = []
        for cell in row.cells:
            text = " ".join(cell.text.split())
            # A merged cell is returned once for each grid column it spans.
            if text and (not cells or cells[-1] != text):
                cells.append(text)
        if cells:
            rows.append(" | ".join(cells))
    return Passage(text="\n".join(rows))


class PdfTextReader:
    """Each page's paragraphs with the page number. A PDF whose pages hold no text (scanned
    pages, which would need text recognition) is refused."""

    def read(self, content: bytes) -> Sequence[Passage]:
        if b"%PDF-" not in content[:_PDF_HEADER_WINDOW]:
            raise DocumentRejectedError(Rejection.WRONG_TYPE)
        try:
            passages = self._passages(content)
        except DocumentRejectedError:
            raise
        # pypdf's own limits on decompressed streams, so a small file cannot unpack to gigabytes.
        except LimitReachedError as error:
            raise DocumentRejectedError(Rejection.TOO_LARGE_UNPACKED) from error
        # The library raises many kinds of error on damaged input.
        except Exception as error:
            raise DocumentRejectedError(Rejection.DAMAGED) from error
        if not passages:
            raise DocumentRejectedError(Rejection.NO_TEXT)
        return passages

    def _passages(self, content: bytes) -> list[Passage]:
        reader = PdfReader(io.BytesIO(content), strict=False)
        # A PDF may be encrypted only to restrict printing or copying, with an empty password to
        # open it; that one is read. One that needs a password to open is refused.
        if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
            raise DocumentRejectedError(Rejection.PASSWORD_PROTECTED)
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentRejectedError(Rejection.TOO_LARGE_UNPACKED)
        return [
            Passage(text=paragraph, page=number)
            for number, page in enumerate(reader.pages, start=1)
            for paragraph in _paragraphs(_page_text(page))
        ]


def _page_text(page: PageObject) -> str:
    """Layout mode keeps the vertical gaps between paragraphs as blank lines; plain mode, the
    fallback for a page layout mode cannot handle, has no paragraphs but keeps every word."""
    try:
        return page.extract_text(extraction_mode="layout")
    except LimitReachedError:
        raise
    except Exception:
        return page.extract_text()


def _paragraphs(page_text: str) -> list[str]:
    paragraphs: list[str] = []
    for chunk in _BLANK_LINES.split(page_text):
        lines = [clean_line(line) for line in chunk.split("\n")]
        paragraph = "\n".join(line for line in lines if line)
        if paragraph:
            paragraphs.append(paragraph)
    return paragraphs


class _Caption(Protocol):
    """The part of webvtt-py's caption this reader uses; the library has no type hints."""

    @property
    def text(self) -> str: ...
    @property
    def start(self) -> str: ...
    @property
    def voice(self) -> str | None: ...


class WebVttReader:
    """Each caption with its start time and its voice tag (`<v Dana Ruiz>`) as the speaker;
    styling tags are dropped and character references decoded."""

    def read(self, content: bytes) -> Sequence[Passage]:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise DocumentRejectedError(Rejection.DAMAGED) from error
        if not text.startswith("WEBVTT"):
            raise DocumentRejectedError(Rejection.WRONG_TYPE)
        try:
            captions = list(cast("Iterable[_Caption]", webvtt.from_string(text).captions))
        # The library raises its own errors on malformed files, and others on odd timings.
        except Exception as error:
            raise DocumentRejectedError(Rejection.DAMAGED) from error
        # The library skips a caption whose timing it cannot read; losing its words silently
        # would leave the source incomplete, so the file is refused instead.
        timings = sum(1 for line in text.splitlines() if "-->" in line)
        if timings != len(captions) or (not captions and text[len("WEBVTT") :].strip()):
            raise DocumentRejectedError(Rejection.DAMAGED)
        return [
            Passage(
                text=html.unescape(caption.text),
                start_ms=_cue_time_ms(caption.start),
                speaker=html.unescape(caption.voice) if caption.voice else None,
            )
            for caption in captions
        ]


def _cue_time_ms(timestamp: str) -> int | None:
    match = _CUE_TIME.match(timestamp)
    if match is None:
        return None
    hours, minutes, seconds, millis = (int(part or 0) for part in match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


DOCUMENT_READERS: DocumentReaders = {
    MediaType.WORD: WordReader(),
    MediaType.PDF: PdfTextReader(),
    MediaType.WEBVTT: WebVttReader(),
}
