"""Speaker labels found in transcripts. Every name here is fictional."""

from pathlib import Path

import pytest

from scopesteps.sources.domain.speakers import (
    DetectedSpeaker,
    detect_speakers,
    speakers_by_paragraph,
)

REPO = Path(__file__).parents[3]


def labels(text: str) -> list[tuple[str, int]]:
    return [(speaker.label, speaker.turn_count) for speaker in detect_speakers(text)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            "Mira Holt: Hello.\n\nTomas Reed: Hi.",
            [("Mira Holt", 1), ("Tomas Reed", 1)],
            id="zoom-meet",
        ),
        pytest.param(
            "**Mira:** Hello.\n\n**Tomas:** Hi.", [("Mira", 1), ("Tomas", 1)], id="bold-inside"
        ),
        pytest.param(
            "**Mira**: Hello.\n\n**Tomas**: Hi.", [("Mira", 1), ("Tomas", 1)], id="bold-outside"
        ),
        pytest.param(
            "Mira (Workshop lead): Hello.\n\nTomas (Front desk): Hi.",
            [("Mira", 1), ("Tomas", 1)],
            id="name-and-role",
        ),
        pytest.param(
            "**Dana (Facilities):** Hello.\n\n**Sam (Student Union):** Hi.",
            [("Dana", 1), ("Sam", 1)],
            id="bold-name-and-role",
        ),
        pytest.param(
            "WEBVTT\n\n1\n00:00:00.000 --> 00:00:03.000\n<v Mira Holt>Hello.</v>\n\n"
            "2\n00:00:03.000 --> 00:00:05.000\n<v Tomas Reed>Hi.</v>",
            [("Mira Holt", 1), ("Tomas Reed", 1)],
            id="teams-vtt",
        ),
        pytest.param(
            "Mira Holt   0:03\nHello, everyone.\n\nTomas Reed   0:15\nHi.",
            [("Mira Holt", 1), ("Tomas Reed", 1)],
            id="teams-text",
        ),
        pytest.param("Mira Holt   1:02:03\nHello.", [("Mira Holt", 1)], id="teams-text-hours"),
        pytest.param(
            "[00:01:02] Mira: Hello.\n\n00:01:09 Tomas: Hi.\n\n(0:12) - Ana: Hey.",
            [("Mira", 1), ("Tomas", 1), ("Ana", 1)],
            id="leading-timestamps",
        ),
        pytest.param(
            "00:00:01\nMira: Hello.\n00:00:04\nTomas: Hi.",
            [("Mira", 1), ("Tomas", 1)],
            id="timestamp-lines",
        ),
        pytest.param(
            "Mira: Hello.\nTomas: Hi.\nMira: Bye.",
            [("Mira", 2), ("Tomas", 1)],
            id="one-line-turns-in-one-paragraph",
        ),
        pytest.param(
            "Sam: Students want a room.\n\nSam: Could societies book weekly?\n\nDana: No.",
            [("Sam", 1), ("Dana", 1)],
            id="consecutive-turns-by-one-speaker",
        ),
        pytest.param(
            "Zoë Ångström: Hej.\n\nJosé María O\u2019Neill: Hola.\n\n李雷: 你好。",
            [("Zoë Ångström", 1), ("José María O\u2019Neill", 1), ("李雷", 1)],
            id="unicode-names",
        ),
        pytest.param(
            "Speaker 1: Hello.\n\nSpeaker 2: Hi.\n\nSpeaker 1: Bye.",
            [("Speaker 1", 2), ("Speaker 2", 1)],
            id="numbered-speakers",
        ),
    ],
)
def test_detects_each_format(text: str, expected: list[tuple[str, int]]) -> None:
    assert labels(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("One two three four five six: too many words.", [], id="over-five-words"),
        pytest.param(f"{'A' * 61}: too long.", [], id="over-sixty-characters"),
        pytest.param("Note: bring snacks.", [], id="note"),
        pytest.param("Agenda: room booking.", [], id="agenda"),
        pytest.param("Action items: write it up.", [], id="action-items"),
        pytest.param("Attendees: Mira Holt, Tomas Reed.", [], id="attendees"),
        pytest.param("Kickoff meeting: Bike Repair Workshop Sign-up", [], id="title"),
        pytest.param("# Kickoff meeting: Campus Room Booking", [], id="markdown-heading"),
        pytest.param("See https://example.org/page for details.", [], id="url"),
        pytest.param("1234: digits only.", [], id="digits"),
        pytest.param("<b>Mira</b>: markup.", [], id="markup"),
        pytest.param("We meet at the library.\nMira: not a turn start.", [], id="mid-paragraph"),
        pytest.param(
            "Mira Holt   0:03\nWe start at 9:30\nTomas: a line inside Mira's turn.",
            [("Mira Holt", 1)],
            id="inside-a-header-turn",
        ),
        pytest.param(
            "Mira Holt: Hello.\nThe plan is simple.\nShe said: we start at nine.",
            [("Mira Holt", 1)],
            id="continuation-line",
        ),
    ],
)
def test_ignores_what_is_not_a_speaker(text: str, expected: list[tuple[str, int]]) -> None:
    assert labels(text) == expected


def test_matches_labels_by_key_and_keeps_the_first_spelling() -> None:
    speakers = detect_speakers("Mira  Holt: Hello.\n\nTomas: Hi.\n\nMIRA HOLT: Bye.")

    assert [(s.label, s.key, s.turn_count) for s in speakers] == [
        ("Mira Holt", "mira holt", 2),
        ("Tomas", "tomas", 1),
    ]


def test_records_the_first_block_and_a_plain_text_sample_of_the_first_turn() -> None:
    text = (
        "# Kickoff\n\n"
        "Mira Holt   0:03\nThe main problem is people arriving when every stand is taken.\n\n"
        "<v Tomas Reed>Half the calls are about <b>space</b> &amp; slots.</v>\n\n"
        f"Ana: {'word ' * 60}"
    )

    mira, tomas, ana = detect_speakers(text)

    assert mira == DetectedSpeaker(
        label="Mira Holt",
        key="mira holt",
        turn_count=1,
        first_block_ordinal=2,
        sample="The main problem is people arriving when every stand is taken.",
    )
    assert tomas.first_block_ordinal == 3
    assert tomas.sample == "Half the calls are about <b>space</b> &amp; slots."
    assert len(ana.sample) == 160
    assert ana.sample.endswith("…")


def test_the_sample_transcript_names_its_three_speakers_and_not_its_pasted_note() -> None:
    text = (REPO / "samples/sources/valid/transcript.txt").read_text()

    assert labels(text) == [("Mira", 5), ("Tomas", 3), ("Ana", 3)]


def test_the_room_booking_fixture_names_its_four_speakers() -> None:
    text = (REPO / "apps/api/tests/fixtures/room_booking/transcript.md").read_text()

    assert [label for label, _ in labels(text)] == ["Alex", "Dana", "Priya", "Sam"]


def test_a_document_without_labels_has_no_speakers() -> None:
    assert detect_speakers("We agreed to book rooms online.\n\nPayments are out of scope.") == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            "# Kickoff\n\nMira: Hello.\n\nTomas: Hi.",
            {2: ("mira",), 3: ("tomas",)},
            id="one-speaker-a-paragraph",
        ),
        pytest.param(
            "Mira: Hello.\nTomas: Hi.\nMira: Bye.",
            {1: ("mira", "tomas")},
            id="several-in-one-paragraph",
        ),
        pytest.param(
            "Mira Holt   0:03\nFirst point.\n\nA second paragraph of Mira's turn.\n\nAna: Yes.",
            {1: ("mira holt",), 2: ("mira holt",), 3: ("ana",)},
            id="a-turn-running-on",
        ),
        pytest.param(
            "Mira: Hello.\n\nShe went on.\n<v Tomas>Then me.</v>",
            {1: ("mira",), 2: ("mira", "tomas")},
            id="running-on-then-a-new-speaker",
        ),
        pytest.param("Notes without labels.\n\nMore notes.", {}, id="no-speech"),
    ],
)
def test_speakers_by_paragraph(text: str, expected: dict[int, tuple[str, ...]]) -> None:
    assert speakers_by_paragraph(text) == expected
