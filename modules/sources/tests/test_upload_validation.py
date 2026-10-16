import hashlib

import pytest

from scopesteps.kernel.errors import DomainError
from scopesteps.sources.domain.errors import (
    EmptySourceError,
    SourceTooLargeError,
    SourceWordLimitError,
    UnreadableSourceError,
    UnsupportedSourceTypeError,
)
from scopesteps.sources.domain.source import MediaType, SourceKind
from scopesteps.sources.domain.upload import (
    SourceLimits,
    UploadedFile,
    check_word_limit,
    display_filename,
    parse_uploads,
    request_fingerprint,
)

LIMITS = SourceLimits(max_bytes=1024, max_words=50)


def _file(
    content: bytes, filename: str = "brief.md", kind: SourceKind = SourceKind.BRIEF
) -> UploadedFile:
    return UploadedFile(kind=kind, filename=filename, content=content)


def test_a_valid_upload_is_split_into_located_paragraphs() -> None:
    content = b"# Brief\r\n\r\nStudents book rooms.\r\n\r\nNo recurring bookings."

    [source] = parse_uploads([_file(content)], LIMITS)

    assert source.media_type is MediaType.MARKDOWN
    assert source.checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert source.byte_size == len(content)
    assert source.word_count == 8
    assert [block.ordinal for block in source.blocks] == [1, 2, 3]
    for block in source.blocks:
        assert source.text[block.start_offset : block.end_offset] == block.text


def test_parsing_the_same_bytes_twice_gives_the_same_locators() -> None:
    content = b"One.\n\nTwo.\n\n\nThree."

    first = parse_uploads([_file(content)], LIMITS)
    second = parse_uploads([_file(content)], LIMITS)

    assert first == second


def test_a_byte_order_mark_is_not_part_of_the_text() -> None:
    [source] = parse_uploads([_file(b"\xef\xbb\xbfHello")], LIMITS)

    assert source.text == "Hello"


@pytest.mark.parametrize(
    ("filename", "media_type"),
    [
        ("notes.txt", MediaType.PLAIN_TEXT),
        ("NOTES.TXT", MediaType.PLAIN_TEXT),
        ("brief.md", MediaType.MARKDOWN),
        ("brief.markdown", MediaType.MARKDOWN),
    ],
)
def test_the_file_extension_decides_the_media_type(filename: str, media_type: MediaType) -> None:
    [source] = parse_uploads([_file(b"Text", filename)], LIMITS)

    assert source.media_type is media_type


@pytest.mark.parametrize(
    ("file", "error", "code"),
    [
        (_file(b"Text", "brief.pdf"), UnsupportedSourceTypeError, "UNSUPPORTED_SOURCE_TYPE"),
        (_file(b"Text", "brief"), UnsupportedSourceTypeError, "UNSUPPORTED_SOURCE_TYPE"),
        (_file(b"Text", ""), UnsupportedSourceTypeError, "UNSUPPORTED_SOURCE_TYPE"),
        (_file(b"x" * 1025), SourceTooLargeError, "SOURCE_TOO_LARGE"),
        (_file(b"caf\xe9"), UnreadableSourceError, "SOURCE_UNREADABLE"),
        (_file(b"PK\x03\x04binary"), UnreadableSourceError, "SOURCE_UNREADABLE"),
        (_file(b""), EmptySourceError, "SOURCE_EMPTY"),
        (_file(b" \n\n\t\n"), EmptySourceError, "SOURCE_EMPTY"),
    ],
)
def test_invalid_files_are_rejected_naming_the_field(
    file: UploadedFile, error: type[DomainError], code: str
) -> None:
    with pytest.raises(error) as raised:
        parse_uploads([file], LIMITS)

    assert raised.value.code == code
    assert raised.value.details["field"] == "brief"


def test_a_file_exactly_at_the_size_limit_is_accepted() -> None:
    [source] = parse_uploads([_file(b"x" * 1024)], LIMITS)

    assert source.byte_size == 1024


def test_the_word_limit_counts_current_sources_and_the_upload_together() -> None:
    with pytest.raises(SourceWordLimitError) as raised:
        check_word_limit(current_words=30, added_words=21, limits=LIMITS)

    assert raised.value.details == {"word_count": 51, "current_word_count": 30, "max_words": 50}


def test_sources_exactly_at_the_word_limit_are_accepted() -> None:
    check_word_limit(current_words=30, added_words=20, limits=LIMITS)


def test_files_are_validated_one_by_one_regardless_of_the_word_limit() -> None:
    files = [_file(b"word " * 40), _file(b"word " * 40, "notes.txt", SourceKind.TRANSCRIPT)]

    sources = parse_uploads(files, LIMITS)

    assert [source.word_count for source in sources] == [40, 40]


def test_a_rejection_names_the_file_so_one_of_several_can_be_found() -> None:
    files = [_file(b"Fine."), _file(b"", "notes.md", SourceKind.SUPPORTING_DOCUMENT)]

    with pytest.raises(EmptySourceError) as raised:
        parse_uploads(files, LIMITS)

    assert raised.value.message == "notes.md has no text. Add some text to it and upload again."
    assert raised.value.details == {"field": "supporting_document", "filename": "notes.md"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("brief.md", "brief.md"),
        ("../../etc/passwd.txt", "passwd.txt"),
        ("C:\\Users\\dana\\brief.md", "brief.md"),
        ("  brief\x00\n.md ", "brief.md"),
        ("a" * 300 + ".md", "a" * 252 + ".md"),
    ],
)
def test_filenames_are_reduced_to_display_names(raw: str, expected: str) -> None:
    assert display_filename(raw) == expected


def test_rejections_never_echo_the_document_text() -> None:
    with pytest.raises(UnreadableSourceError) as raised:
        parse_uploads([_file(b"secret roadmap \x00")], LIMITS)

    assert "secret" not in raised.value.message
    assert "secret" not in str(raised.value.details)


def test_fingerprint_changes_with_content_filename_and_kind() -> None:
    base = _file(b"Text")

    fingerprints = {
        request_fingerprint([base]),
        request_fingerprint([_file(b"Other")]),
        request_fingerprint([_file(b"Text", "other.md")]),
        request_fingerprint([_file(b"Text", kind=SourceKind.TRANSCRIPT)]),
        request_fingerprint([base], target="019a3a5e-0000-7000-8000-000000000001"),
    }

    assert len(fingerprints) == 5
    assert request_fingerprint([base]) == request_fingerprint([_file(b"Text")])
