from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

BRIEF = "# Brief\n\nUsers can book a room.\n"
TRANSCRIPT = "# Meeting\n\n**A:** Leave recurring bookings out.\n"
CHANGE_REQUEST = "Please add recurring bookings.\n"

PackFactory = Callable[..., Path]


def _default_annotations(pack_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "pack": {"id": pack_id, "title": "Demo", "summary": "Demo pack"},
        "annotations": [
            {
                "id": "CR-01",
                "kind": "confirmed_requirement",
                "statement": "Users can book a room.",
                "expect": "include",
                "evidence": [{"file": "brief.md", "paragraph": 2, "quote": "book a room"}],
            },
            {
                "id": "MD-01",
                "kind": "missing_decision",
                "statement": "Cancellation rules are undecided.",
                "expect": "ask",
            },
        ],
    }


@pytest.fixture
def make_pack(tmp_path: Path) -> PackFactory:
    """Write a valid pack under tmp_path/<split>/<pack_id>; keyword overrides replace files."""

    def factory(
        pack_id: str = "demo",
        split: str = "dev",
        *,
        brief: str = BRIEF,
        annotations: dict[str, Any] | None = None,
        answers: list[dict[str, Any]] | None = None,
        transcript: str = TRANSCRIPT,
        speakers: list[dict[str, Any]] | None = None,
    ) -> Path:
        pack_dir = tmp_path / split / pack_id
        pack_dir.mkdir(parents=True)
        (pack_dir / "brief.md").write_text(brief)
        (pack_dir / "transcript.md").write_text(transcript)
        if speakers is not None:
            (pack_dir / "speakers.yaml").write_text(
                yaml.safe_dump({"schema_version": 1, "speakers": speakers})
            )
        (pack_dir / "change_request.txt").write_text(CHANGE_REQUEST)
        (pack_dir / "annotations.yaml").write_text(
            yaml.safe_dump(annotations or _default_annotations(pack_id))
        )
        (pack_dir / "clarification_answers.yaml").write_text(
            yaml.safe_dump({"schema_version": 1, "answers": answers or []})
        )
        return pack_dir

    return factory
