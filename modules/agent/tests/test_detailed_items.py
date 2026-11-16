"""draft-v8: fuller epics and stories, and epics that carry their own acceptance criteria.

All data is synthetic.
"""

import json
from typing import Any

from scopesteps.agent.application.checks import DETAIL_CHECKS, PEOPLE_CHECKS, check_draft
from scopesteps.agent.application.drafting import (
    DRAFT_PROMPTS,
    PROMPT_CHECKS,
    PROMPT_SCHEMAS,
    draft_single_pass,
    prompt_version,
)
from scopesteps.agent.application.schemas import (
    DraftBacklogV4,
    SourceBlockInput,
)
from scopesteps.agent.domain.model import ModelResult, ModelTurn, Usage
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider

BLOCKS = [SourceBlockInput("B1", "brief", "Users can book a room.")]
BOOK = {"block_id": "B1", "quote": "book a room"}
EPIC_CRITERION: dict[str, Any] = {
    "text": "When a user books a room, the office sees the booking.",
    "origin": "proposed",
    "citations": [],
}


def _epic(**changes: Any) -> dict[str, Any]:
    epic: dict[str, Any] = {
        "ref": "E1",
        "kind": "epic",
        "parent_ref": None,
        "title": "Booking",
        "description": "Users book rooms themselves. The office no longer takes bookings by phone.",
        "criteria": [EPIC_CRITERION],
        "assumptions": [],
        "open_questions": [],
        "covers": [],
    }
    return epic | changes


def _draft(epic: dict[str, Any]) -> dict[str, Any]:
    return {
        "statements": [
            {"id": "T1", "kind": "confirmed", "summary": "Book a room", "citations": [BOOK]}
        ],
        "items": [
            epic,
            {
                "ref": "S1",
                "kind": "story",
                "parent_ref": "E1",
                "title": "Book",
                "description": (
                    "As a user, I want to book a room, so that I can study.\n\n"
                    "Today the office takes every booking by phone."
                ),
                "criteria": [
                    {"text": "A room is booked.", "origin": "source", "citations": [BOOK]}
                ],
                "assumptions": [],
                "open_questions": [],
                "covers": ["T1"],
            },
        ],
        "questions": [],
        "people": [],
    }


def _result(text: str) -> ModelResult:
    return ModelResult(
        "t", "m", ModelTurn(({"type": "model_output"},)), text, (), "completed", Usage(), 1
    )


def test_draft_v8_asks_for_fuller_items_and_leaves_draft_v7_as_measured() -> None:
    v8 = DRAFT_PROMPTS["draft-v8"]

    assert "one to three acceptance criteria" in v8
    assert "after a blank line, add one to\n  three sentences of context" in v8
    assert "both sides of its limit or deadline" in v8
    assert "one-sentence description and no criteria" not in v8
    assert v8.endswith(
        DRAFT_PROMPTS["draft-v7"][DRAFT_PROMPTS["draft-v7"].index("Open decisions:") :]
    )
    assert prompt_version("draft-v7") == "draft-v7+608c373e10be"
    assert PROMPT_SCHEMAS["draft-v8"] == PROMPT_SCHEMAS["draft-v7"] == "draft-backlog.v4"
    assert PROMPT_CHECKS["draft-v7"] == PEOPLE_CHECKS
    assert PROMPT_CHECKS["draft-v8"] == DETAIL_CHECKS


def test_under_draft_v8_an_epic_needs_criteria() -> None:
    assert (
        check_draft(DraftBacklogV4.model_validate(_draft(_epic())), BLOCKS, enabled=DETAIL_CHECKS)
        == []
    )
    assert check_draft(
        DraftBacklogV4.model_validate(_draft(_epic(criteria=[]))), BLOCKS, enabled=DETAIL_CHECKS
    ) == [
        "epic E1 has no acceptance criteria; add the outcomes that hold once its stories are done"
    ]


def test_draft_v7_still_keeps_criteria_off_epics() -> None:
    assert check_draft(
        DraftBacklogV4.model_validate(_draft(_epic())), BLOCKS, enabled=PEOPLE_CHECKS
    ) == ["epic E1 has acceptance criteria; put them on its stories"]
    assert (
        check_draft(
            DraftBacklogV4.model_validate(_draft(_epic(criteria=[]))), BLOCKS, enabled=PEOPLE_CHECKS
        )
        == []
    )


def test_an_epic_without_criteria_is_repaired_with_a_patch_of_that_epic() -> None:
    bare = json.dumps(_draft(_epic(criteria=[])))
    patch = json.dumps({"statements": [], "items": [_epic()], "questions": [], "people": []})
    provider = ScriptedProvider([_result(bare), _result(patch)])

    outcome = draft_single_pass(provider, BLOCKS, max_output_tokens=100, prompt="draft-v8")

    assert (outcome.repair, outcome.repaired, outcome.check_problems) == ("targeted", True, ())
    assert outcome.repair_triggers == ("epic_without_criteria",)
    assert isinstance(outcome.draft, DraftBacklogV4)
    assert [c.text for c in outcome.draft.items[0].criteria] == [EPIC_CRITERION["text"]]
    assert "- epic E1 has no acceptance criteria" in str(provider.requests[1].history[2])
