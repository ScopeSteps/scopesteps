from typing import Any

import pytest

from scopesteps.agent.application.checks import check_draft
from scopesteps.agent.application.schemas import DraftBacklogV1 as DraftBacklog
from scopesteps.agent.application.schemas import SourceBlockInput

BLOCKS = [
    SourceBlockInput("B1", "brief", "Users can book a room."),
    SourceBlockInput("B2", "transcript", "**Dana:** We need a rule for no-shows."),
    SourceBlockInput("U1", "open decision", "No-show rule: reviewer did not answer."),
]
BOOK = {"block_id": "B1", "quote": "book a room"}
NO_SHOW = {"block_id": "B2", "quote": "Dana: We need a rule for no-shows."}


def _story(**overrides: Any) -> dict[str, Any]:
    story: dict[str, Any] = {
        "ref": "S1",
        "kind": "story",
        "parent_ref": "E1",
        "title": "Book",
        "description": "As a student, I want to book a room, so that I can study.",
        "criteria": [{"text": "Booking succeeds", "origin": "source", "citations": [BOOK]}],
        "assumptions": [],
        "open_questions": [],
    }
    return story | overrides


def _draft(**overrides: Any) -> DraftBacklog:
    epic: dict[str, Any] = {
        "ref": "E1",
        "kind": "epic",
        "parent_ref": None,
        "title": "Booking",
        "description": "Booking rooms.",
        "criteria": [],
        "assumptions": [],
        "open_questions": [],
    }
    data: dict[str, Any] = {
        "statements": [{"kind": "open_question", "summary": "No-shows", "citations": [NO_SHOW]}],
        "items": [epic, _story()],
        "questions": [
            {"subject": "No-shows", "question": "?", "why_it_matters": "!", "citations": [NO_SHOW]}
        ],
    }
    return DraftBacklog.model_validate(data | overrides)


def test_a_complete_draft_passes() -> None:
    assert check_draft(_draft(), BLOCKS) == []


@pytest.mark.parametrize(
    ("draft", "kwargs", "problem"),
    [
        (
            _draft(questions=[]),
            {},
            "open_question 'No-shows' has no clarification question citing B2",
        ),
        (_draft(), {"open_decision_blocks": {"U1"}}, "open decision U1 is unresolved"),
        (
            _draft(items=[_draft().items[0].model_dump(), _story(description="Book a room")]),
            {},
            "story S1 description is not 'As a <role>, I want ...'",
        ),
        (
            _draft(
                items=[
                    _draft().items[0].model_dump()
                    | {"criteria": [{"text": "x", "origin": "source", "citations": [BOOK]}]},
                    _story(),
                ]
            ),
            {},
            "epic E1 has acceptance criteria",
        ),
        (
            _draft(items=[_draft().items[0].model_dump(), _story(criteria=[])]),
            {},
            "story S1 has no acceptance criteria",
        ),
        (
            _draft(
                items=[
                    _draft().items[0].model_dump(),
                    _story(
                        criteria=[
                            {
                                "text": "x",
                                "origin": "source",
                                "citations": [{"block_id": "B1", "quote": "invented"}],
                            }
                        ]
                    ),
                ]
            ),
            {},
            "S1 criterion quote is not verbatim from B1",
        ),
        (
            _draft(
                items=[
                    _draft().items[0].model_dump(),
                    _story(
                        criteria=[
                            {
                                "text": "x",
                                "origin": "source",
                                "citations": [{"block_id": "B9", "quote": "x"}],
                            }
                        ]
                    ),
                ]
            ),
            {},
            "S1 criterion cites unknown block B9",
        ),
    ],
)
def test_problems_are_reported(draft: DraftBacklog, kwargs: dict[str, Any], problem: str) -> None:
    problems = check_draft(draft, BLOCKS, **kwargs)

    assert any(found.startswith(problem) for found in problems), problems


def test_user_story_format_accepts_an() -> None:
    draft = _draft(
        items=[_draft().items[0].model_dump(), _story(description="As an admin, I want x")]
    )

    assert check_draft(draft, BLOCKS) == []
