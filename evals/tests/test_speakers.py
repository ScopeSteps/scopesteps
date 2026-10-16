"""Confirmed speakers in evaluation packs, as real users provide them (ADR 0012). Synthetic."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scopesteps.agent.client import SpeakerNote
from scopesteps.evals.packs import PackError, load_pack, load_packs
from scopesteps.evals.scoring import build_inputs

PackFactory = Callable[..., Path]
TRANSCRIPT = (
    "# Meeting\n\nSynthetic transcript.\n\n"
    "**Mira:** Leave recurring bookings out.\n\n"
    "**Guest 1:** Can we pay for parts?\n\n"
    "**Tomas:** Agreed."
)
MAPPING: list[dict[str, Any]] = [
    {"label": "Mira", "name": "Mira Holt", "meeting_role": "Sponsor"},
    {"label": "Guest 1", "not_a_person": True},
    {"label": "Tomas", "name": "Tomas Reed"},
]


def test_transcript_blocks_carry_the_pack_s_confirmed_speakers(make_pack: PackFactory) -> None:
    pack = load_pack(make_pack(transcript=TRANSCRIPT, speakers=MAPPING), "dev")

    blocks = {block.label: block for block in build_inputs(pack, "initial").blocks}

    assert blocks["transcript.md paragraph 2"].speakers == ()
    assert blocks["transcript.md paragraph 3"].speakers == (
        SpeakerNote("Mira", "Mira Holt", "Sponsor"),
    )
    assert blocks["transcript.md paragraph 4"].speakers == (
        SpeakerNote("Guest 1", not_a_person=True),
    )
    assert blocks["transcript.md paragraph 5"].speakers == (SpeakerNote("Tomas", "Tomas Reed"),)
    assert blocks["brief.md paragraph 2"].speakers == ()


def test_a_pack_without_a_mapping_shows_its_speakers_as_unconfirmed(
    make_pack: PackFactory,
) -> None:
    pack = load_pack(make_pack(transcript=TRANSCRIPT), "dev")

    notes = [b.speakers for b in build_inputs(pack, "initial").blocks if b.speakers]

    assert notes == [(SpeakerNote("Mira"),), (SpeakerNote("Guest 1"),), (SpeakerNote("Tomas"),)]


@pytest.mark.parametrize(
    ("speakers", "problem"),
    [
        (MAPPING[:2], "speaker 'tomas' is not confirmed"),
        ([*MAPPING, {"label": "Ana", "name": "Ana Lund"}], "no speaker 'ana' in the transcript"),
        ([{"label": "Mira"}], "give a name, or mark the label not_a_person"),
        (
            [{"label": "Guest 1", "not_a_person": True, "meeting_role": "QA"}],
            "has no meeting role",
        ),
        ([*MAPPING, {"label": "mira", "name": "Mira H."}], "Duplicate speaker labels"),
    ],
)
def test_a_mapping_must_answer_for_exactly_the_transcript_s_labels(
    make_pack: PackFactory, speakers: list[dict[str, Any]], problem: str
) -> None:
    with pytest.raises(PackError, match=problem):
        load_pack(make_pack(transcript=TRANSCRIPT, speakers=speakers), "dev")


def test_dev_transcripts_carry_no_attendee_list_or_inline_roles() -> None:
    for pack in load_packs("dev"):
        text = pack.source_text("transcript.md")

        assert "Attendees:" not in text, pack.id
        assert pack.speakers is not None, pack.id
        assert all("(" not in note.label for notes in pack.notes.values() for note in notes)
        assert all(note.name is not None for notes in pack.notes.values() for note in notes), (
            f"{pack.id}: every speaker is confirmed"
        )
