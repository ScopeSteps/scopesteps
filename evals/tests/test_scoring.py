from typing import Any

import pytest

from scopesteps.agent.client import DraftBacklogV1 as DraftBacklog
from scopesteps.evals.packs import DATASETS_DIR, Pack, load_pack
from scopesteps.evals.scoring import PackInputs, build_inputs, score_draft


@pytest.fixture(scope="module")
def campus() -> Pack:
    return load_pack(DATASETS_DIR / "dev" / "campus-room-booking", "dev")


def _cite(inputs: PackInputs, file: str, paragraph: int) -> dict[str, str]:
    block_id = inputs.block_ids_by_paragraph[(file, paragraph)]
    text = next(block.text for block in inputs.blocks if block.id == block_id)
    return {"block_id": block_id, "quote": text[:40]}


def _quote(inputs: PackInputs, file: str, paragraph: int, quote: str) -> dict[str, str]:
    return {"block_id": inputs.block_ids_by_paragraph[(file, paragraph)], "quote": quote}


def _good_draft(inputs: PackInputs) -> dict[str, Any]:
    def criterion(file: str, paragraph: int, quote: str) -> dict[str, Any]:
        return {
            "text": quote,
            "origin": "source",
            "citations": [_quote(inputs, file, paragraph, quote)],
        }

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
                    # Brief paragraphs 6 and 8 and transcript 16 each state several
                    # requirements, so each is quoted by its own criterion.
                    criterion("brief.md", 8, "book an individual one-off slot"),
                    criterion("brief.md", 8, "sign in with their existing college account"),
                    criterion("brief.md", 8, "search rooms by date, time and capacity"),
                    criterion("brief.md", 8, "can block a room for maintenance"),
                    criterion("brief.md", 6, "Reduce double bookings to zero."),
                    criterion("brief.md", 6, "a single view of all bookings"),
                    criterion("transcript.md", 5, "reject an overlapping booking"),
                    criterion("transcript.md", 16, "my office needs to see who booked each room"),
                    criterion("transcript.md", 16, "Students should only see that a room is taken"),
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
    assert matched["CR-01"].startswith("E1: book an individual one-off slot")
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
    assert inputs.open_decision_block_by_annotation == {"MD-02": "U1"}
    assert [block.id for block in inputs.blocks][-3:] == ["A1", "A2", "U1"]
    assert next(b for b in inputs.blocks if b.id == "U1").label == "open decision"


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


def test_skipped_decisions_pass_when_the_open_decision_block_is_asked_about(campus: Pack) -> None:
    inputs = build_inputs(campus, "with_answers")
    draft = _good_draft(inputs)
    draft["questions"] = [
        {
            "subject": "no-show",
            "question": "?",
            "why_it_matters": "!",
            "citations": [{"block_id": "U1", "quote": "The reviewer has not answered this yet"}],
        }
    ]

    card = score_draft(campus, inputs, DraftBacklog.model_validate(draft))

    assert {r.annotation_id: r.verdict for r in card.results}["MD-02"] == "pass"


def test_story_quality_metrics(campus: Pack) -> None:
    inputs = build_inputs(campus, "initial")
    draft = _good_draft(inputs)
    story = draft["items"][0] | {"ref": "S1", "kind": "story", "parent_ref": "E1"}
    draft["items"].append(story | {"description": "As a student, I want to book, so that I study."})
    draft["items"].append(story | {"ref": "S2", "description": "Booking rooms"})

    card = score_draft(campus, inputs, DraftBacklog.model_validate(draft))

    assert card.epics_with_criteria == 1
    assert card.user_story_format_rate == 0.5


def test_story_detail_is_counted(campus: Pack) -> None:
    inputs = build_inputs(campus, "initial")
    draft = _good_draft(inputs)
    story: dict[str, Any] = {
        "kind": "story",
        "parent_ref": "E1",
        "title": "Book",
        "criteria": [{"text": "c", "origin": "proposed", "citations": []}] * 3,
        "assumptions": [],
        "open_questions": [],
    }
    draft["items"] += [
        story | {"ref": "S1", "description": "As a student, I want a room.\n\nRooms run out."},
        story | {"ref": "S2", "description": "As a student, I want to cancel.", "criteria": []},
    ]

    card = score_draft(campus, inputs, DraftBacklog.model_validate(draft))

    assert (card.criteria_per_story, card.story_context_rate) == (1.5, 0.5)


def _criteria(draft: dict[str, Any], *criteria: dict[str, Any]) -> dict[str, Any]:
    draft["items"][0]["criteria"] = list(criteria)
    return draft


def test_citing_a_paragraph_that_states_several_requirements_proves_only_what_it_states(
    campus: Pack,
) -> None:
    inputs = build_inputs(campus, "initial")
    slot = _quote(inputs, "brief.md", 8, "book an individual one-off slot")
    draft = _criteria(
        _good_draft(inputs),
        {"text": "A user books a one-off slot.", "origin": "source", "citations": [slot]},
        {
            "text": "Students and staff sign in with their existing college account.",
            "origin": "source",
            "citations": [slot],
        },
    )

    card = score_draft(campus, inputs, DraftBacklog.model_validate(draft))

    verdicts = {r.annotation_id: r.verdict for r in card.results}
    assert verdicts["CR-01"] == "pass", "its own sentence is quoted"
    assert verdicts["CR-03"] == "pass", "a criterion states its key terms"
    assert verdicts["CR-04"] == verdicts["CR-05"] == "needs_review"


def test_committing_one_side_of_an_unanswered_conflict_is_unsupported(campus: Pack) -> None:
    inputs = build_inputs(campus, "initial")
    four = _quote(inputs, "brief.md", 8, "A booking can last up to 4 hours.")
    draft = _good_draft(inputs)
    draft["items"][0]["criteria"].append(
        {"text": "A booking lasts at most 4 hours.", "origin": "source", "citations": [four]}
    )

    card = score_draft(campus, inputs, DraftBacklog.model_validate(draft))

    assert card.unsupported_commitments == 1


def test_one_side_of_a_conflict_backed_by_the_answer_is_supported(campus: Pack) -> None:
    inputs = build_inputs(campus, "with_answers")
    three = _quote(inputs, "transcript.md", 10, "three hours is the most")
    answer = next(b.text for b in inputs.blocks if b.id == "A1")
    draft = _good_draft(inputs)
    draft["items"][0]["criteria"].append(
        {
            "text": "A booking lasts at most 3 hours.",
            "origin": "source",
            "citations": [three, {"block_id": "A1", "quote": answer}],
        }
    )

    card = score_draft(campus, inputs, DraftBacklog.model_validate(draft))

    assert card.unsupported_commitments == 0


def test_a_misquote_is_counted_apart_from_an_unsupported_claim(campus: Pack) -> None:
    inputs = build_inputs(campus, "initial")
    draft = _good_draft(inputs)
    draft["items"][0]["criteria"] += [
        {
            "text": "A user books a one-off slot.",
            "origin": "source",
            "citations": [_quote(inputs, "brief.md", 8, "book an individal one-off slot")],
        },
        {
            "text": "Bookings sync to calendars.",
            "origin": "source",
            "citations": [_quote(inputs, "brief.md", 8, "bookings sync to every calendar")],
        },
    ]

    card = score_draft(campus, inputs, DraftBacklog.model_validate(draft))

    assert (card.near_verbatim_quotes, card.unsupported_commitments) == (1, 1)
