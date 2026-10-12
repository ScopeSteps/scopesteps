import pytest

from scopesteps.sources.client import quote_matches, split_into_blocks


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


@pytest.mark.parametrize(
    ("quote", "block", "matches"),
    [
        (
            "Dana (Facilities): Not in the first release.",
            "**Dana (Facilities):** Not in the first release.",
            True,
        ),
        ("let\u2019s leave it", "so let's leave it out", True),
        ("book  an\nindividual slot", "book an individual slot", True),
        ("use the `snake_case` name", "use the snake_case name", True),
        ("Not in the second release.", "**Dana:** Not in the first release.", False),
        ("leave recurring bookings in", "leave recurring bookings out", False),
        ("Use &lt;b&gt; &amp; more", "Use <b> & more", True),
        ("", "anything", False),
        ("**", "anything", False),
    ],
)
def test_quotes_match_ignoring_formatting_but_not_wording(
    quote: str, block: str, matches: bool
) -> None:
    assert quote_matches(quote, block) is matches
