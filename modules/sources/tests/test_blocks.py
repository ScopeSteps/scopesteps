import pytest

from scopesteps.sources.client import split_into_blocks


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("One.\n\nTwo.", ["One.", "Two."]),
        ("One.\r\n\r\nTwo.", ["One.", "Two."]),
        ("- a\n- b\n\nNext", ["- a\n- b", "Next"]),
        ("\n\n  One.  \n \n\n\nTwo.\n", ["One.", "Two."]),
        ("", []),
        ("   \n\n  ", []),
    ],
)
def test_split_into_blocks_uses_blank_lines(text: str, expected: list[str]) -> None:
    assert [block.text for block in split_into_blocks(text)] == expected


def test_ordinals_start_at_one_and_offsets_locate_the_text() -> None:
    text = "# Title\n\n  First paragraph.\n\nSecond."

    blocks = split_into_blocks(text)

    assert [block.ordinal for block in blocks] == [1, 2, 3]
    for block in blocks:
        assert text[block.start_offset : block.end_offset] == block.text
