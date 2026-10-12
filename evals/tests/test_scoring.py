from typing import Any

import pytest

from scopesteps.agent.client import DraftBacklog
from scopesteps.evals.packs import DATASETS_DIR, Pack, load_pack
from scopesteps.evals.scoring import PackInputs, build_inputs, score_draft


@pytest.fixture(scope="module")
def campus() -> Pack:
    return load_pack(DATASETS_DIR / "dev" / "campus-room-booking", "dev")


def _cite(inputs: PackInputs, file: str, paragraph: int) -> dict[str, str]:
    block_id = inputs.block_ids_by_paragraph[(file, paragraph)]
    text = next(block.text for block in inputs.blocks if block.id == block_id)
    return {"block_id": block_id, "quote": text[:40]}


def _good_draft(inputs: PackInputs) -> dict[str, Any]:
    def criterion(file: str, paragraph: int) -> dict[str, Any]:
        return {"text": "c", "origin": "source", "citations": [_cite(inputs, file, paragraph)]}

    return {
        "statements": [
            {
                "kind": "exclusion",
                "summary": "no recurring",
                "citations": [_cite(inputs, "transcript.md", 8)],
            },
            {
                "kind": "proposal",
                "summary": "outlook",
                "citations": [_cite(inputs, "transcript.md", 11)],
            },
        ],
        "items": [
            {
                "ref": "E1",
                "kind": "epic",
                "parent_ref": None,
                "title": "Booking",
                "description": "",
                "criteria": [
                    criterion("brief.md", 8),
                    criterion("brief.md", 6),
                    criterion("transcript.md", 5),
                    criterion("transcript.md", 16),
                ],
                "assumptions": [],
                "open_questions": [],
            }
        ],
        "questions": [
            {
                "subject": s,
                "question": "?",
                "why_it_matters": "!",
                "citations": [_cite(inputs, f, p)],
            }
            for s, f, p in [
                ("length", "transcript.md", 10),
                ("cancel", "brief.md", 10),
                ("no-show", "transcript.md", 13),
            ]
        ],
    }


def test_a_draft_that_handles_every_annotation_passes(campus: Pack) -> None:
    inputs = build_inputs(campus, "initial")

    card = score_draft(campus, inputs, DraftBacklog.model_validate(_good_draft(inputs)))

    failed = [r.annotation_id for r in card.results if r.verdict != "pass"]
    assert failed == []
    matched = {r.annotation_id: r.matched for r in card.results}
    assert matched["CR-01"].startswith("E1: c")
    assert matched["CF-01"] == "Q: ?"
    assert matched["EX-01"] == "exclusion: no recurring"
    assert card.citation_accuracy == 1
    assert card.unsupported_commitments == 0
    assert {r.annotation_id for r in card.results}.isdisjoint({"CI-01", "CI-02"})


def test_committing_excluded_work_fails_and_counts_as_unsupported(campus: Pack) -> None:
    inputs = build_inputs(campus, "initial")
    draft = _good_draft(inputs)
    draft["items"][0]["criteria"].append(
        {"text": "weekly", "origin": "source", "citations": [_cite(inputs, "transcript.md", 8)]}
    )

    card = score_draft(campus, inputs, DraftBacklog.model_validate(draft))

    verdicts = {r.annotation_id: r.verdict for r in card.results}
    assert verdicts["EX-01"] == "fail"
    assert card.unsupported_commitments == 1


def test_missing_coverage_and_bad_quotes_are_detected(campus: Pack) -> None:
    inputs = build_inputs(campus, "initial")
    draft = _good_draft(inputs)
    draft["items"][0]["criteria"] = [
        {
            "text": "c",
            "origin": "source",
            "citations": [{"block_id": "B8", "quote": "invented words"}],
        }
    ]

    card = score_draft(campus, inputs, DraftBacklog.model_validate(draft))

    verdicts = {r.annotation_id: r.verdict for r in card.results}
    assert verdicts["CR-07"] == "fail"
    assert card.unsupported_commitments == 1
    assert card.citation_accuracy is not None
    assert card.citation_accuracy < 1


def test_answers_mode_adds_only_answered_initial_questions(campus: Pack) -> None:
    inputs = build_inputs(campus, "with_answers")

    assert inputs.answer_block_by_annotation == {"CF-01": "A1", "MD-01": "A2"}
    assert [block.id for block in inputs.blocks][-2:] == ["A1", "A2"]


def test_answered_decisions_must_be_used_and_skipped_ones_still_asked(campus: Pack) -> None:
    inputs = build_inputs(campus, "with_answers")
    draft = _good_draft(inputs)
    answer_text = next(b.text for b in inputs.blocks if b.id == "A1")
    draft["items"][0]["criteria"].append(
        {"text": "3h", "origin": "source", "citations": [{"block_id": "A1", "quote": answer_text}]}
    )

    card = score_draft(campus, inputs, DraftBacklog.model_validate(draft))

    verdicts = {r.annotation_id: r.verdict for r in card.results}
    assert verdicts["CF-01"] == "pass"
    assert verdicts["MD-01"] == "fail"
    assert verdicts["MD-02"] == "pass"
