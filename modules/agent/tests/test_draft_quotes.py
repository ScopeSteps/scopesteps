"""draft-v9: quotes come only from a block's text, never from its speakers attribute.

All data is synthetic.
"""

import json
from typing import Any

from scopesteps.agent.application.checks import DETAIL_CHECKS, check_draft
from scopesteps.agent.application.drafting import (
    DRAFT_PROMPTS,
    PROMPT_CHECKS,
    PROMPT_SCHEMAS,
    draft_single_pass,
    prompt_version,
    sources_message,
)
from scopesteps.agent.application.schemas import DraftBacklogV4, SourceBlockInput, SpeakerNote
from scopesteps.agent.domain.model import ModelResult, ModelTurn, Usage
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider

RULE = """\
- Quote only from the text inside a source tag, never from its attributes. For example, quote
  "Three hours is the most I want", not "Dana Ruiz, Sponsor".
"""
DANA = SpeakerNote("Dana", "Dana Ruiz", "Sponsor")
BLOCKS = [
    SourceBlockInput("B1", "brief", "Users can book a room."),
    SourceBlockInput(
        "B2", "transcript paragraph 1", "Dana: Three hours is the most I want.", (DANA,)
    ),
]
BOOK = {"block_id": "B1", "quote": "book a room"}


def _draft(person_quote: str) -> dict[str, Any]:
    return {
        "statements": [
            {"id": "T1", "kind": "confirmed", "summary": "Book a room", "citations": [BOOK]},
            {
                "id": "T2",
                "kind": "context",
                "summary": "Booking length",
                "citations": [{"block_id": "B2", "quote": "Three hours is the most I want."}],
            },
        ],
        "items": [
            {
                "ref": "E1",
                "kind": "epic",
                "parent_ref": None,
                "title": "Booking",
                "description": "Users book rooms themselves.",
                "criteria": [
                    {"text": "Bookings are self-service.", "origin": "proposed", "citations": []}
                ],
                "assumptions": [],
                "open_questions": [],
                "covers": [],
            },
            {
                "ref": "S1",
                "kind": "story",
                "parent_ref": "E1",
                "title": "Book",
                "description": "As a user, I want to book a room, so that I can study.",
                "criteria": [
                    {"text": "A room is booked.", "origin": "source", "citations": [BOOK]}
                ],
                "assumptions": [],
                "open_questions": [],
                "covers": ["T1"],
            },
        ],
        "questions": [],
        "people": [
            {
                "ref": "P1",
                "name": "Dana Ruiz",
                "role": "Sponsor",
                "said": "Dana wants bookings to last at most three hours.",
                "citations": [{"block_id": "B2", "quote": person_quote}],
                "rights": "not_stated",
                "rights_citations": [],
            }
        ],
    }


def _result(text: str) -> ModelResult:
    return ModelResult(
        "t", "m", ModelTurn(({"type": "model_output"},)), text, (), "completed", Usage(), 1
    )


def test_draft_v9_is_draft_v8_plus_the_quoting_rule_and_v7_and_v8_are_unchanged() -> None:
    v8, v9 = DRAFT_PROMPTS["draft-v8"], DRAFT_PROMPTS["draft-v9"]

    assert RULE not in v8
    assert v9.replace(RULE, "", 1) == v8
    assert prompt_version("draft-v7") == "draft-v7+608c373e10be"
    assert prompt_version("draft-v8") == "draft-v8+11a8c1740cb1"
    assert PROMPT_SCHEMAS["draft-v9"] == PROMPT_SCHEMAS["draft-v8"] == "draft-backlog.v4"
    assert PROMPT_CHECKS["draft-v9"] == PROMPT_CHECKS["draft-v8"] == DETAIL_CHECKS
    assert sources_message(BLOCKS, "", "draft-v9") == sources_message(BLOCKS, "", "draft-v8")


def test_a_quote_from_the_speakers_attribute_is_named_as_such_only_under_draft_v9() -> None:
    draft = DraftBacklogV4.model_validate(_draft("Dana Ruiz, Sponsor"))

    named = check_draft(draft, BLOCKS, enabled=DETAIL_CHECKS, attribute_quotes=True)
    as_measured = check_draft(draft, BLOCKS, enabled=DETAIL_CHECKS)

    assert named == [
        "person P1 quote is from the speakers attribute of B2, not its text; quote only the "
        "text inside the tag: 'Dana Ruiz, Sponsor'"
    ]
    assert as_measured == ["person P1 quote is not verbatim from B2"]


def test_a_quote_in_neither_the_text_nor_the_attribute_keeps_the_plain_message() -> None:
    draft = DraftBacklogV4.model_validate(_draft("Four hours is fine."))

    assert check_draft(draft, BLOCKS, enabled=DETAIL_CHECKS, attribute_quotes=True) == [
        "person P1 quote is not verbatim from B2"
    ]


def test_a_draft_v9_repair_request_names_the_attribute() -> None:
    first = json.dumps(_draft("Dana Ruiz, Sponsor"))
    fixed = json.dumps(_draft("Three hours is the most I want."))
    patch = json.dumps(
        {"statements": [], "items": [], "questions": [], "people": json.loads(fixed)["people"]}
    )
    provider = ScriptedProvider([_result(first), _result(patch)])

    outcome = draft_single_pass(provider, BLOCKS, max_output_tokens=100, prompt="draft-v9")

    assert outcome.repair_triggers == ("quote_not_verbatim",)
    assert (outcome.repaired, outcome.check_problems) == (True, ())
    repair = str(provider.requests[1].history[2])
    assert "quote is from the speakers attribute of B2, not its text" in repair
