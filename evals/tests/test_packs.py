from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from scopesteps.evals.manifest import heldout_present
from scopesteps.evals.packs import PackError, load_pack, load_packs

PackFactory = Callable[..., Path]


def test_valid_pack_loads_with_paragraph_blocks(make_pack: PackFactory) -> None:
    pack = load_pack(make_pack(), "dev")

    assert pack.id == "demo"
    assert [block.text for block in pack.blocks["brief.md"]] == [
        "# Brief",
        "Users can book a room.",
    ]


def _with_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "pack": {"id": "demo", "title": "Demo", "summary": "Demo pack"},
        "annotations": [
            {
                "id": "CR-01",
                "kind": "confirmed_requirement",
                "statement": "Users can book a room.",
                "expect": "include",
                "evidence": [evidence],
            }
        ],
    }


@pytest.mark.parametrize(
    ("kwargs", "problem"),
    [
        (
            {
                "annotations": _with_evidence(
                    {"file": "brief.md", "paragraph": 2, "quote": "a desk"}
                )
            },
            "quote not found in brief.md paragraph 2",
        ),
        (
            {"annotations": _with_evidence({"file": "brief.md", "paragraph": 9, "quote": "room"})},
            "brief.md has no paragraph 9",
        ),
        (
            {"annotations": _with_evidence({"file": "notes.md", "paragraph": 1, "quote": "room"})},
            "notes.md is not a source file of this pack",
        ),
        (
            {"answers": [{"question_for": "CR-01", "answered_by": "Sponsor", "answer": "Yes"}]},
            "does not expect a question",
        ),
        (
            {"answers": [{"question_for": "ZZ-99", "answered_by": "Sponsor", "answer": None}]},
            "unknown annotation ZZ-99",
        ),
        (
            {
                "answers": [
                    {"question_for": "MD-01", "answered_by": "Sponsor", "answer": "Yes"},
                    {"question_for": "MD-01", "answered_by": "Sponsor", "answer": None},
                ]
            },
            "more than one answer for MD-01",
        ),
        ({"brief": "Users can book a room.\n\n" + "word " * 6000}, "words (max 6000)"),
    ],
)
def test_pack_problems_are_reported(
    make_pack: PackFactory, kwargs: dict[str, Any], problem: str
) -> None:
    pack_dir = make_pack(**kwargs)

    with pytest.raises(PackError) as raised:
        load_pack(pack_dir, "dev")

    assert any(problem in reported for reported in raised.value.problems)


def test_pack_id_must_match_folder(make_pack: PackFactory) -> None:
    pack_dir = make_pack("other-name")
    annotations = yaml.safe_load((pack_dir / "annotations.yaml").read_text())
    annotations["pack"]["id"] = "demo"
    (pack_dir / "annotations.yaml").write_text(yaml.safe_dump(annotations))

    with pytest.raises(PackError, match="does not match folder name"):
        load_pack(pack_dir, "dev")


def test_missing_files_are_reported(make_pack: PackFactory) -> None:
    pack_dir = make_pack()
    (pack_dir / "change_request.txt").unlink()

    with pytest.raises(PackError, match=r"missing change_request\.txt"):
        load_pack(pack_dir, "dev")


def test_repository_dev_packs_are_valid() -> None:
    packs = load_packs("dev")

    assert len(packs) >= 2
    assert {"campus-room-booking"} <= {pack.id for pack in packs}


@pytest.mark.skipif(not heldout_present(), reason="held-out packs are not cloned")
def test_repository_heldout_packs_are_valid() -> None:
    # Validates structure only; the assertion never prints held-out content.
    load_packs("heldout")


def test_supporting_documents_follow_the_brief_and_transcript(make_pack: PackFactory) -> None:
    pack_dir = make_pack()
    (pack_dir / "supporting-rooms.txt").write_text("Room list.\n\nRoom 1 seats four.\n")
    (pack_dir / "supporting-faq.md").write_text("# FAQ\n")
    (pack_dir / "notes.md").write_text("Not a source: no supporting- prefix.\n")

    pack = load_pack(pack_dir, "dev")

    assert pack.initial_files == (
        "brief.md",
        "transcript.md",
        "supporting-faq.md",
        "supporting-rooms.txt",
    )
    assert [block.text for block in pack.blocks["supporting-rooms.txt"]] == [
        "Room list.",
        "Room 1 seats four.",
    ]
    assert "notes.md" not in pack.blocks


def test_supporting_documents_count_towards_the_word_limit(make_pack: PackFactory) -> None:
    pack_dir = make_pack()
    (pack_dir / "supporting-long.md").write_text("word " * 6000)

    with pytest.raises(PackError, match="initial sources total"):
        load_pack(pack_dir, "dev")
