"""Reading Word, PDF and WebVTT files into source text and blocks (ADR 0025).

Every file here is synthetic and built by the test that reads it. The PDF builder writes the
file by hand: no library this project uses can write text into a PDF.
"""

import io
import time
import zipfile
import zlib
from collections.abc import Sequence

import docx
import pytest
from pypdf import PdfReader, PdfWriter

from scopesteps.kernel.errors import DomainError, InvalidInputError, UnsupportedMediaTypeError
from scopesteps.sources.application.upload import parse_uploads
from scopesteps.sources.domain.documents import (
    MAX_TURN_CHARS,
    DocumentRejectedError,
    Passage,
    Rejection,
    assemble,
    caption_turns,
)
from scopesteps.sources.domain.source import MediaType, SourceKind
from scopesteps.sources.domain.speakers import detect_speakers, is_turn_header, turn_start
from scopesteps.sources.domain.upload import SourceLimits, UploadedFile
from scopesteps.sources.infrastructure import documents
from scopesteps.sources.infrastructure.documents import (
    DOCUMENT_READERS,
    PdfTextReader,
    WebVttReader,
    WordReader,
)

# Synthetic passwords for building encrypted test files.
OPEN_PASSWORD = "synthetic-open-password"  # noqa: S105
OWNER_PASSWORD = "synthetic-owner-password"  # noqa: S105
LIMITS = SourceLimits(max_bytes=4096, max_words=5000, max_document_bytes=1024 * 1024)

_LINE_HEIGHT = 14
_TOP = 740


def build_word(paragraphs: Sequence[str], table: Sequence[Sequence[str]] = ()) -> bytes:
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for row, values in zip(grid.rows, table, strict=True):
            for cell, value in zip(row.cells, values, strict=True):
                cell.text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_pdf(
    pages: Sequence[Sequence[str]],
    password: str | None = None,
    owner_password: str | None = None,
    flate_padding: int = 0,
) -> bytes:
    """One page per entry, each a list of lines; an empty line leaves a paragraph gap, and a page
    with no lines has no text at all, like a scanned page.

    `password` is needed to open the file; `owner_password` alone only restricts it.
    `flate_padding` compresses each page's content with that many spaces of padding after it.
    """
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages_id = len(objects) + 1 + 2 * len(pages)
    kids: list[int] = []
    for lines in pages:
        operations = ["BT /F1 11 Tf"]
        y = _TOP
        for line in lines:
            if line:
                escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                operations.append(f"1 0 0 1 72 {y} Tm ({escaped}) Tj")
            y -= _LINE_HEIGHT
        operations.append("ET")
        stream = "\n".join(operations).encode("latin-1")
        filter_entry = b""
        if flate_padding:
            stream = zlib.compress(stream + b"\n" + b" " * flate_padding, 9)
            filter_entry = b" /Filter /FlateDecode"
        contents = add(
            b"<< /Length %d%s >>\nstream\n%s\nendstream" % (len(stream), filter_entry, stream)
        )
        kids.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
                b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (pages_id, contents, font)
            )
        )
    references = b" ".join(b"%d 0 R" % kid for kid in kids)
    add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (references, len(kids)))
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n%s\nendobj\n" % (number, body))
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, catalog, xref)
    )
    if password is None and owner_password is None:
        return out.getvalue()
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(out.getvalue())))
    writer.encrypt(
        user_password=password or "", owner_password=owner_password or password, algorithm="AES-128"
    )
    encrypted = io.BytesIO()
    writer.write(encrypted)
    return encrypted.getvalue()


def build_zip_bomb(unpacked_bytes: int) -> bytes:
    """A small .docx whose main part unpacks to `unpacked_bytes` of spaces."""
    word = build_word(["Room booking."])
    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(word)) as source,
        zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bomb,
    ):
        for part in source.infolist():
            if part.filename == "word/document.xml":
                bomb.writestr(part.filename, b" " * unpacked_bytes)
            else:
                bomb.writestr(part, source.read(part))
    return buffer.getvalue()


def build_word_with_part(name: str, content: bytes) -> bytes:
    """A real .docx with one part replaced."""
    word = build_word(["Room booking."])
    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(word)) as source,
        zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as changed,
    ):
        for part in source.infolist():
            changed.writestr(part, content if part.filename == name else source.read(part))
    return buffer.getvalue()


def _parse(filename: str, content: bytes, kind: SourceKind = SourceKind.BRIEF):
    [parsed] = parse_uploads(
        [UploadedFile(kind=kind, filename=filename, content=content)], LIMITS, DOCUMENT_READERS
    )
    return parsed


def _rejection(reader: WordReader | PdfTextReader | WebVttReader, content: bytes) -> Rejection:
    with pytest.raises(DocumentRejectedError) as raised:
        reader.read(content)
    return raised.value.reason


# Word


def test_word_paragraphs_and_tables_become_passages_in_order() -> None:
    content = build_word(
        ["Room booking brief", "Staff book rooms by the hour.", "   "],
        table=[["Room", "Seats"], ["Study room", "4"]],
    )

    passages = WordReader().read(content)

    assert [p.text for p in passages if p.text.strip()] == [
        "Room booking brief",
        "Staff book rooms by the hour.",
        "Room: Study room | Seats: 4",
    ]


def test_word_headings_list_items_and_each_table_row_are_paragraphs_in_reading_order() -> None:
    document = docx.Document()
    document.add_heading("Workshop brief", level=1)
    document.add_paragraph("Book a stand", style="List Bullet")
    document.add_paragraph("Cancel a booking", style="List Bullet")
    table = document.add_table(rows=3, cols=2)
    for row, values in zip(
        table.rows, [("Stand", "Open"), ("Stand 1", "Saturdays"), ("Stand 2", "")], strict=True
    ):
        for cell, value in zip(row.cells, values, strict=True):
            cell.text = value
    document.add_paragraph("Payments are out of scope.")
    buffer = io.BytesIO()
    document.save(buffer)

    passages = WordReader().read(buffer.getvalue())

    assert [p.text for p in passages] == [
        "Workshop brief",
        "Book a stand",
        "Cancel a booking",
        "Stand: Stand 1 | Open: Saturdays",
        "Stand: Stand 2",
        "Payments are out of scope.",
    ]


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"Plain text saved with a .docx name", Rejection.WRONG_TYPE),
        # An old binary .doc, and a password-protected .docx, are both OLE compound files.
        (bytes.fromhex("d0cf11e0a1b11ae1") + b"\x00" * 512, Rejection.WRONG_TYPE),
        (
            bytes.fromhex("d0cf11e0a1b11ae1") + "EncryptedPackage".encode("utf-16-le"),
            Rejection.PASSWORD_PROTECTED,
        ),
        (b"PK\x03\x04 truncated archive", Rejection.DAMAGED),
    ],
)
def test_word_files_that_are_not_readable_documents_are_refused(
    content: bytes, reason: Rejection
) -> None:
    assert _rejection(WordReader(), content) == reason


def test_a_word_zip_bomb_is_refused_before_it_is_unpacked() -> None:
    bomb = build_zip_bomb(documents.MAX_WORD_UNPACKED_BYTES + 1)
    started = time.perf_counter()

    reason = _rejection(WordReader(), bomb)

    assert reason is Rejection.TOO_LARGE_UNPACKED
    assert len(bomb) < 1024 * 1024
    assert time.perf_counter() - started < 1


def test_a_macro_enabled_word_document_is_refused() -> None:
    content_types = zipfile.ZipFile(io.BytesIO(build_word(["x"]))).read("[Content_Types].xml")
    macro = content_types.replace(
        b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        b"application/vnd.ms-word.document.macroEnabled.main+xml",
    )

    reason = _rejection(WordReader(), build_word_with_part("[Content_Types].xml", macro))

    assert reason is Rejection.WRONG_TYPE


def test_a_word_document_with_broken_xml_is_damaged() -> None:
    broken = build_word_with_part("word/document.xml", b"<w:document><w:body>")

    assert _rejection(WordReader(), broken) is Rejection.DAMAGED


def test_entities_in_a_word_document_are_never_expanded() -> None:
    laughs = (
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "lollollollollollollollol">'
        b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;"><!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">'
        b'<!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">]>'
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<w:body><w:p><w:r><w:t>&d;</w:t></w:r></w:p></w:body></w:document>"
    )

    passages = WordReader().read(build_word_with_part("word/document.xml", laughs))

    assert "".join(p.text for p in passages) == ""


# PDF


def test_pdf_paragraphs_keep_their_page_numbers() -> None:
    content = build_pdf(
        [
            [
                "Room booking brief",
                "",
                "Staff book rooms by the hour.",
                "Students book study rooms.",
            ],
            ["Recurring bookings are out of scope."],
        ]
    )

    passages = PdfTextReader().read(content)

    assert passages == [
        Passage("Room booking brief", page=1),
        Passage("Staff book rooms by the hour.\nStudents book study rooms.", page=1),
        Passage("Recurring bookings are out of scope.", page=2),
    ]


def test_a_pdf_with_only_an_owner_password_is_read() -> None:
    content = build_pdf([["Staff book rooms by the hour."]], owner_password=OWNER_PASSWORD)

    assert PdfTextReader().read(content) == [Passage("Staff book rooms by the hour.", page=1)]


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"Plain text saved with a .pdf name", Rejection.WRONG_TYPE),
        (build_pdf([["Staff book rooms."]])[:200], Rejection.DAMAGED),
        (build_pdf([[], []]), Rejection.NO_TEXT),
        (build_pdf([["Staff book rooms."]], password=OPEN_PASSWORD), Rejection.PASSWORD_PROTECTED),
    ],
    ids=["not-a-pdf", "truncated", "scanned", "password"],
)
def test_pdfs_that_cannot_be_read_are_refused(content: bytes, reason: Rejection) -> None:
    assert _rejection(PdfTextReader(), content) == reason


def test_a_pdf_with_too_many_pages_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents, "MAX_PDF_PAGES", 2)

    reason = _rejection(PdfTextReader(), build_pdf([["One."], ["Two."], ["Three."]]))

    assert reason is Rejection.TOO_LARGE_UNPACKED


def test_a_pdf_stream_that_unpacks_too_far_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    # pypdf's own cap, lowered so the test stays small and quick.
    monkeypatch.setattr("pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH", 1024 * 1024)
    bomb = build_pdf([["Staff book rooms."]], flate_padding=4 * 1024 * 1024)

    reason = _rejection(PdfTextReader(), bomb)

    assert reason is Rejection.TOO_LARGE_UNPACKED
    assert len(bomb) < 64 * 1024


# WebVTT


VTT = b"""WEBVTT

1
00:00:03.000 --> 00:00:05.000
<v Mira Holt>We open the workshop at nine.</v>

2
00:00:05.500 --> 00:00:07.000
<v Mira Holt>Six stands &amp; one lead.</v>

3
00:14:32.120 --> 00:14:35.000
<v Tomas Reed>Half the calls ask whether there is <b>space</b>.</v>

4
01:02:03.000 --> 01:02:05.000
<v Mira Holt>One slot per person.</v>
"""


def test_webvtt_captions_keep_their_voice_and_start_time() -> None:
    passages = WebVttReader().read(VTT)

    assert passages[1] == Passage("Six stands & one lead.", start_ms=5500, speaker="Mira Holt")
    assert passages[2] == Passage(
        "Half the calls ask whether there is space.", start_ms=872_120, speaker="Tomas Reed"
    )
    assert passages[3].start_ms == 3_723_000


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"Mira: not a caption file", Rejection.WRONG_TYPE),
        (b"WEBVTT\n\n00:00:01.000 --> nonsense\nWords", Rejection.DAMAGED),
        (
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nr\u00e9sum\u00e9".encode("latin-1"),
            Rejection.DAMAGED,
        ),
    ],
    ids=["no-header", "bad-timing", "not-utf8"],
)
def test_webvtt_files_that_cannot_be_read_are_refused(content: bytes, reason: Rejection) -> None:
    assert _rejection(WebVttReader(), content) == reason


def test_a_webvtt_transcript_becomes_one_paragraph_per_turn_with_times_and_speakers() -> None:
    parsed = _parse("kickoff.vtt", VTT, SourceKind.TRANSCRIPT)

    assert parsed.media_type is MediaType.WEBVTT
    assert [(b.text, b.start_ms, b.speaker) for b in parsed.blocks] == [
        ("Mira Holt: We open the workshop at nine. Six stands & one lead.", 3000, "Mira Holt"),
        ("Tomas Reed: Half the calls ask whether there is space.", 872_120, "Tomas Reed"),
        ("Mira Holt: One slot per person.", 3_723_000, "Mira Holt"),
    ]
    assert [(s.label, s.turn_count) for s in detect_speakers(parsed.text)] == [
        ("Mira Holt", 2),
        ("Tomas Reed", 1),
    ]


def test_a_long_turn_is_split_near_the_paragraph_length() -> None:
    sentence = "We need more repair stands on Saturday mornings."
    captions = [Passage(sentence, start_ms=i * 1000, speaker="Mira") for i in range(60)]

    turns = caption_turns(captions)

    assert len(turns) > 1
    assert all(len(turn.text) <= MAX_TURN_CHARS + len("Mira: ") for turn in turns)
    assert all(turn.text.startswith("Mira: ") for turn in turns)
    assert turns[1].start_ms is not None
    assert turns[1].start_ms > 0


# Word transcripts and text transcripts


def test_a_teams_word_transcript_puts_each_header_with_its_turn() -> None:
    content = build_word(
        [
            "Kickoff meeting",
            "Mira Holt   0:03",
            "We open the workshop at nine.",
            "Tomas Reed   14:32",
            "Half the calls ask whether there is space.",
        ]
    )

    parsed = _parse("kickoff.docx", content, SourceKind.TRANSCRIPT)

    assert [(b.text, b.start_ms, b.speaker) for b in parsed.blocks] == [
        ("Kickoff meeting", None, None),
        ("Mira Holt   0:03\nWe open the workshop at nine.", 3000, "Mira Holt"),
        ("Tomas Reed   14:32\nHalf the calls ask whether there is space.", 872_000, "Tomas Reed"),
    ]
    assert [s.label for s in detect_speakers(parsed.text)] == ["Mira Holt", "Tomas Reed"]


def test_a_word_brief_keeps_headers_that_look_like_names_as_paragraphs() -> None:
    parsed = _parse("brief.docx", build_word(["Mira Holt   0:03", "Workshop brief."]))

    assert [b.text for b in parsed.blocks] == ["Mira Holt   0:03", "Workshop brief."]
    assert all(b.speaker is None and b.start_ms is None for b in parsed.blocks)


def test_text_transcript_paragraphs_get_the_speaker_and_time_they_start_with() -> None:
    content = b"Kickoff\n\n[00:01:05] Mira: We open at nine.\n\nTomas: Six stands.\n\nAnd one lead."

    parsed = _parse("kickoff.txt", content, SourceKind.TRANSCRIPT)

    assert [(b.start_ms, b.speaker) for b in parsed.blocks] == [
        (None, None),
        (65_000, "Mira"),
        (None, "Tomas"),
        (None, None),
    ]


def test_a_pdf_brief_is_stored_with_located_paragraphs_and_pages() -> None:
    content = build_pdf(
        [["Room booking brief", "", "Staff book rooms."], ["Out of scope: payments."]]
    )

    parsed = _parse("brief.pdf", content)

    assert parsed.media_type is MediaType.PDF
    assert [(b.ordinal, b.page) for b in parsed.blocks] == [(1, 1), (2, 1), (3, 2)]
    for block in parsed.blocks:
        assert parsed.text[block.start_offset : block.end_offset] == block.text
    assert parsed.word_count == 10
    assert parsed.byte_size == len(content)


# Rules shared by every format


def test_each_passage_becomes_exactly_one_block() -> None:
    text, blocks = assemble(
        [
            Passage("First line\n\n\nsame paragraph", page=1),
            Passage("   "),
            Passage("Tab\tand NUL\x00 removed", page=2),
        ]
    )

    assert text == "First line\nsame paragraph\n\nTab\tand NUL removed"
    assert [(b.text, b.page) for b in blocks] == [
        ("First line\nsame paragraph", 1),
        ("Tab\tand NUL removed", 2),
    ]


@pytest.mark.parametrize(
    ("reason", "error", "code"),
    [
        (Rejection.WRONG_TYPE, UnsupportedMediaTypeError, "SOURCE_TYPE_MISMATCH"),
        (Rejection.PASSWORD_PROTECTED, InvalidInputError, "SOURCE_PASSWORD_PROTECTED"),
        (Rejection.NO_TEXT, InvalidInputError, "SOURCE_SCANNED"),
        (Rejection.DAMAGED, InvalidInputError, "SOURCE_UNREADABLE"),
        (Rejection.TOO_LARGE_UNPACKED, InvalidInputError, "SOURCE_TOO_LARGE_UNPACKED"),
    ],
)
def test_each_refusal_has_its_own_code_and_names_the_file(
    reason: Rejection, error: type[DomainError], code: str
) -> None:
    class Refusing:
        def read(self, content: bytes) -> Sequence[Passage]:
            raise DocumentRejectedError(reason)

    file = UploadedFile(SourceKind.TRANSCRIPT, "kickoff.pdf", b"%PDF-1.7")

    with pytest.raises(DomainError) as raised:
        parse_uploads([file], LIMITS, {MediaType.PDF: Refusing()})

    assert isinstance(raised.value, error)
    assert raised.value.code == code
    assert raised.value.details == {"field": "transcript", "filename": "kickoff.pdf"}
    assert str(raised.value).startswith("kickoff.pdf ")


def test_a_document_has_its_own_size_limit() -> None:
    limits = SourceLimits(max_bytes=10, max_words=5000, max_document_bytes=20)
    brief = UploadedFile(SourceKind.BRIEF, "brief.pdf", b"%PDF-" + b"x" * 20)

    with pytest.raises(DomainError) as raised:
        parse_uploads([brief], limits, DOCUMENT_READERS)

    assert raised.value.code == "SOURCE_TOO_LARGE"
    assert raised.value.details["max_bytes"] == 20


@pytest.mark.parametrize(
    ("paragraph", "speaker", "start_ms"),
    [
        ("Mira: We open at nine.", "Mira", None),
        ("[00:14:32] Mira: We open at nine.", "Mira", 872_000),
        ("Mira Holt   1:02:03\nWe open at nine.", "Mira Holt", 3_723_000),
        ("12\n00:00:05.250 --> 00:00:07.000\n<v Mira>We open.", "Mira", 5250),
        ("Agenda: rooms and stands", None, None),
        ("We open at nine.", None, None),
    ],
)
def test_turn_start_reads_the_label_and_time_a_paragraph_starts_with(
    paragraph: str, speaker: str | None, start_ms: int | None
) -> None:
    found = turn_start(paragraph)

    assert (found.speaker, found.start_ms) == (speaker, start_ms)


@pytest.mark.parametrize(
    ("paragraph", "header"),
    [
        ("Mira Holt   0:03", True),
        ("Mira:", True),
        ("00:00:03.000 --> 00:00:05.000", True),
        ("Mira: We open at nine.", False),
        ("Workshop brief", False),
        ("3", False),
    ],
)
def test_a_turn_header_is_only_a_label_or_a_time(paragraph: str, header: bool) -> None:
    assert is_turn_header(paragraph) is header
