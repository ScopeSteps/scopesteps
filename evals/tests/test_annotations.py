from typing import Any

import pytest
from pydantic import ValidationError

from scopesteps.evals.annotations import Annotation, AnnotationFile

TRANSCRIPT_QUOTE = {"file": "transcript.md", "paragraph": 2, "quote": "text"}
BRIEF_QUOTE = {"file": "brief.md", "paragraph": 1, "quote": "text"}


def _annotation(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "CR-01",
        "kind": "confirmed_requirement",
        "statement": "Users can book a room.",
        "expect": "include",
        "evidence": [BRIEF_QUOTE],
    } | overrides


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"expect": "exclude"}, "cannot expect exclude"),
        ({"evidence": []}, "needs 1\\+ evidence"),
        ({"kind": "conflict", "expect": "ask"}, "needs 2\\+ evidence"),
        ({"kind": "expected_change_impact", "expect": "unchanged"}, "needs relates_to"),
        ({"kind": "expected_change_impact", "expect": "add", "evidence": []}, "needs evidence"),
        (
            {"evidence": [{"file": "change_request.txt", "paragraph": 1, "quote": "x"}]},
            "only change impacts",
        ),
        ({"kind": "exclusion", "expect": "exclude", "relates_to": ["CR-01"]}, "itself"),
        ({"id": "cr-1"}, "pattern"),
        ({"evidence": [{**BRIEF_QUOTE, "paragraph": 0}]}, "greater than or equal to 1"),
        ({"surprise": True}, "Extra inputs"),
    ],
)
def test_invalid_annotations_are_rejected(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Annotation.model_validate(_annotation(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"kind": "missing_decision", "expect": "ask", "evidence": []},
        {"kind": "conflict", "expect": "ask", "evidence": [BRIEF_QUOTE, TRANSCRIPT_QUOTE]},
        {"kind": "expected_change_impact", "expect": "unchanged", "relates_to": ["CR-02"]},
    ],
)
def test_valid_annotations_are_accepted(overrides: dict[str, Any]) -> None:
    Annotation.model_validate(_annotation(**overrides))


def test_change_impacts_are_change_phase() -> None:
    impact = Annotation.model_validate(
        _annotation(kind="expected_change_impact", expect="unchanged", relates_to=["CR-02"])
    )

    assert impact.phase == "change"
    assert Annotation.model_validate(_annotation()).phase == "initial"


@pytest.mark.parametrize(
    ("annotations", "message"),
    [
        ([_annotation(), _annotation()], "Duplicate annotation ids: CR-01"),
        ([_annotation(id="EX-01", relates_to=["CR-09"])], "unknown relates_to CR-09"),
    ],
)
def test_annotation_file_checks_ids(annotations: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        AnnotationFile.model_validate(
            {
                "schema_version": 1,
                "pack": {"id": "demo", "title": "Demo", "summary": "Demo pack"},
                "annotations": annotations,
            }
        )
