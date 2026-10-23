"""The draft-to-candidate mapping: what code guarantees whatever the model wrote."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from scopesteps.agent.application.candidate import to_proposal
from scopesteps.agent.application.drafting import PROMPT_SCHEMAS, draft_single_pass
from scopesteps.agent.application.ports import Passage
from scopesteps.agent.application.schemas import (
    DraftBacklogV3,
    DraftPatchV3,
    SourceBlockInput,
    apply_patch,
)
from scopesteps.agent.domain.budget import RunLimits
from scopesteps.agent.domain.ids import QuestionId, RunId
from scopesteps.agent.domain.model import ModelResult, ModelTurn, Usage
from scopesteps.agent.domain.run import (
    Question,
    QuestionStatus,
    Run,
    RunInputs,
    RunStage,
    RunStatus,
)
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.backlog.client import CandidateProposal, ProposedDecision, ProposedItem
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceBlockId, SourceVersionId

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
REVIEWER = UserId(UUID(int=7))
BRIEF, TRANSCRIPT = SourceVersionId(UUID(int=1)), SourceVersionId(UUID(int=2))
TEXTS = {
    "B1": (BRIEF, "A user can book an individual one-off slot. A booking can last up to 4 hours."),
    "B2": (TRANSCRIPT, "**Dana:** Three hours is the most I want for a single booking."),
    "B3": (TRANSCRIPT, "**Alex:** Recurring reservations are out of scope for release one."),
    "B4": (TRANSCRIPT, "**Dana:** We need a rule for how late someone can cancel."),
}
PASSAGES = {
    label: Passage(SourceBlockId(UUID(int=10 + index)), version, "brief", index, text)
    for index, (label, (version, text)) in enumerate(TEXTS.items(), start=1)
}
BLOCK_IDS = {label: passage.block_id for label, passage in PASSAGES.items()}

BOOK = {"block_id": "B1", "quote": "book an individual one-off slot"}
FOUR_HOURS = {"block_id": "B1", "quote": "A booking can last up to 4 hours."}
THREE_HOURS = {"block_id": "B2", "quote": "Three hours is the most"}
RECURRING = {"block_id": "B3", "quote": "Recurring reservations are out of scope"}
CANCEL_RULE = {"block_id": "B4", "quote": "how late someone can cancel"}
ANSWER = "Up to one hour before the start."

CANCELLATION = Question(
    id=QuestionId(UUID(int=31)),
    run_id=RunId(UUID(int=3)),
    round=1,
    call_id="call-1",
    subject="Cancellation",
    text="How late may a user cancel a booking?",
    why_it_matters="No cancellation rule is agreed.",
    block_labels=("B4",),
    status=QuestionStatus.ANSWERED,
    answer=ANSWER,
    answer_label="A1",
    answered_by=REVIEWER,
    answered_at=NOW,
)
LENGTH = Question(
    id=QuestionId(UUID(int=32)),
    run_id=RunId(UUID(int=3)),
    round=1,
    call_id="call-1",
    subject="Maximum booking length",
    text="Is the maximum booking length three or four hours?",
    why_it_matters="The brief and the transcript disagree.",
    block_labels=("B1", "B2"),
    status=QuestionStatus.SKIPPED,
    answer_label="U1",
    answered_by=REVIEWER,
    answered_at=NOW,
)
RUN = Run(
    id=RunId(UUID(int=3)),
    project_id=ProjectId(UUID(int=9)),
    mode="initial",
    status=RunStatus.RUNNING,
    stage=RunStage.DRAFT,
    revision=4,
    inputs=RunInputs(
        source_version_ids=(BRIEF, TRANSCRIPT),
        provider="test",
        model_id="test-model",
        prompt_version="draft-v4",
        schema_version="draft-backlog.v3",
        limits=RunLimits(
            max_turns=6, max_tool_calls=8, max_output_tokens_per_call=100, max_total_tokens=1000
        ),
        max_clarification_rounds=2,
    ),
    created_by=REVIEWER,
    created_at=NOW,
    updated_at=NOW,
)


def _statement(ref: str, kind: str, *citations: dict[str, str]) -> dict[str, Any]:
    return {"id": ref, "kind": kind, "summary": f"{kind} {ref}", "citations": list(citations)}


def _criterion(text: str, *citations: dict[str, str], origin: str = "source") -> dict[str, Any]:
    return {"text": text, "origin": origin, "citations": list(citations)}


def _story(
    ref: str, *criteria: dict[str, Any], covers: tuple[str, ...] = ("T1",)
) -> dict[str, Any]:
    return {
        "ref": ref,
        "kind": "story",
        "parent_ref": "E1",
        "title": f"Story {ref}",
        "description": "As a student, I want to book a room, so that I can study.",
        "criteria": list(criteria),
        "assumptions": ["Rooms are in the library."],
        "open_questions": [],
        "covers": list(covers),
    }


def _question(*citations: dict[str, str], affects: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "subject": "Booking length",
        "question": "Which maximum applies?",
        "why_it_matters": "The sources disagree.",
        "citations": list(citations),
        "affects": list(affects),
    }


def _draft(
    *stories: dict[str, Any],
    statements: tuple[dict[str, Any], ...] = (),
    questions: tuple[dict[str, Any], ...] = (),
) -> DraftBacklogV3:
    epic: dict[str, Any] = {
        "ref": "E1",
        "kind": "epic",
        "parent_ref": None,
        "title": "Room booking",
        "description": "Booking study rooms.",
        "criteria": [],
        "assumptions": [],
        "open_questions": [],
        "covers": [],
    }
    return DraftBacklogV3.model_validate(
        {
            "statements": [_statement("T1", "confirmed", BOOK), *statements],
            "items": [epic, *stories],
            "questions": list(questions),
        }
    )


def _propose(draft: DraftBacklogV3, *questions: Question) -> CandidateProposal:
    return to_proposal(RUN, draft, PASSAGES, questions)


def _item(proposal: CandidateProposal, ref: str) -> ProposedItem:
    return next(item for item in proposal.items if item.ref == ref)


def _decision(proposal: CandidateProposal, key: str) -> ProposedDecision:
    return next(decision for decision in proposal.decisions if decision.key == key)


def test_labels_become_the_stored_ids_of_the_pinned_paragraphs() -> None:
    proposal = _propose(_draft(_story("S1", _criterion("A user can book a slot.", BOOK))))

    (evidence,) = _item(proposal, "S1").criteria[0].evidence
    assert (evidence.source_version_id, evidence.block_id) == (BRIEF, BLOCK_IDS["B1"])
    assert evidence.quote == "book an individual one-off slot"
    assert (proposal.project_id, proposal.run_id) == (RUN.project_id, RUN.id)
    assert proposal.source_version_ids == (BRIEF, TRANSCRIPT)
    assert _item(proposal, "S1").assumptions == ("Rooms are in the library.",)


@pytest.mark.parametrize(
    "citation",
    [
        {"block_id": "B99", "quote": "book an individual one-off slot"},
        {"block_id": "B1", "quote": "book a recurring slot"},
        {"block_id": "U1", "quote": "has not answered this yet"},
    ],
)
def test_a_citation_that_does_not_resolve_is_dropped_not_stored(citation: dict[str, str]) -> None:
    draft = _draft(_story("S1", _criterion("A user can book a slot.", citation)))

    criterion = _item(_propose(draft, LENGTH), "S1").criteria[0]

    assert criterion.evidence == ()
    assert criterion.confirmed_by == ()


def test_a_criterion_that_quotes_a_reviewer_answer_is_confirmed_by_that_decision() -> None:
    rule = _criterion(
        "A booking can be cancelled up to an hour before.", {"block_id": "A1", "quote": ANSWER}
    )
    draft = _draft(_story("S1", _criterion("Book a slot.", BOOK)), _story("S2", rule))

    proposal = _propose(draft, CANCELLATION)

    assert _item(proposal, "S2").criteria[0].confirmed_by == ("A1",)
    decision = _decision(proposal, "A1")
    assert (decision.status, decision.answer, decision.affects) == ("answered", ANSWER, ("S2",))
    assert (decision.decided_by, decision.decided_at) == (REVIEWER, NOW)
    assert (decision.question_id, decision.question) == (CANCELLATION.id, CANCELLATION.text)
    assert [e.block_id for e in decision.evidence] == [BLOCK_IDS["B4"]]


def test_a_misquoted_answer_confirms_nothing() -> None:
    rule = _criterion("Cancel any time.", {"block_id": "A1", "quote": "Any time before the start."})

    proposal = _propose(_draft(_story("S1", rule)), CANCELLATION)

    assert _item(proposal, "S1").criteria[0].confirmed_by == ()
    assert _decision(proposal, "A1").affects == ()


def test_a_story_does_not_state_a_disputed_value_and_carries_the_conflict() -> None:
    draft = _draft(
        _story(
            "S1",
            _criterion("A user can book a slot.", BOOK),
            _criterion(
                "A booking lasts at most 4 hours.", {"block_id": "B1", "quote": "up to 4 hours"}
            ),
            _criterion("A booking lasts at most 3 hours.", THREE_HOURS, origin="proposed"),
        ),
        _story("S2", _criterion("A user can book a slot.", BOOK)),
        statements=(_statement("T2", "conflict", FOUR_HOURS, THREE_HOURS),),
        questions=(_question(FOUR_HOURS, THREE_HOURS),),
    )

    proposal = _propose(draft)

    assert [c.text for c in _item(proposal, "S1").criteria] == ["A user can book a slot."]
    decision = _decision(proposal, "Q1")
    assert (decision.kind, decision.status, decision.affects) == ("conflict", "open", ("S1",))
    assert {e.relationship for e in decision.evidence} == {"conflicting"}
    assert {e.block_id for e in decision.evidence} == {BLOCK_IDS["B1"], BLOCK_IDS["B2"]}
    assert len(_item(proposal, "S2").criteria) == 1, "the same paragraph, a different sentence"


def test_a_conflict_the_draft_did_not_ask_about_is_still_an_open_decision() -> None:
    draft = _draft(
        _story("S1", _criterion("A booking lasts at most 4 hours.", FOUR_HOURS)),
        statements=(_statement("T2", "conflict", FOUR_HOURS, THREE_HOURS),),
    )

    decision = _decision(_propose(draft), "T2")

    assert (decision.kind, decision.status, decision.affects) == ("conflict", "open", ("S1",))
    assert decision.question.startswith("The sources disagree")


def test_an_answer_settles_the_conflict_it_is_cited_for() -> None:
    settled = replace(
        LENGTH, status=QuestionStatus.ANSWERED, answer="Three hours.", answer_label="A1"
    )
    three = {"block_id": "A1", "quote": "Three hours."}
    draft = _draft(
        _story("S1", _criterion("A booking lasts at most 3 hours.", three, THREE_HOURS)),
        statements=(_statement("T2", "conflict", FOUR_HOURS, THREE_HOURS, three),),
    )

    proposal = _propose(draft, settled)

    assert _item(proposal, "S1").criteria[0].confirmed_by == ("A1",)
    assert [d.key for d in proposal.decisions] == ["A1"]


def test_a_skipped_question_stays_open_even_if_the_draft_does_not_raise_it_again() -> None:
    rule = _criterion("Cancel up to an hour before.", {"block_id": "A1", "quote": ANSWER})

    proposal = _propose(_draft(_story("S1", rule)), CANCELLATION, LENGTH)

    skipped = _decision(proposal, "U1")
    assert (skipped.status, skipped.answer, skipped.affects) == ("skipped", None, ())
    assert (skipped.question_id, skipped.decided_by) == (LENGTH.id, REVIEWER)
    assert _decision(proposal, "A1").status == "answered", "a related answer settles only itself"


def test_a_skipped_question_raised_again_blocks_the_stories_the_draft_names() -> None:
    reraised = _question(
        {"block_id": "U1", "quote": "has not answered this yet"}, FOUR_HOURS, affects=("S1",)
    )
    draft = _draft(
        _story("S1", _criterion("A user can book a slot.", BOOK)),
        statements=(_statement("T2", "conflict", FOUR_HOURS, THREE_HOURS),),
        questions=(reraised, reraised),
    )

    proposal = _propose(draft, LENGTH)

    (decision,) = proposal.decisions
    assert (decision.key, decision.kind, decision.status) == ("U1", "conflict", "skipped")
    assert decision.affects == ("S1",)
    assert decision.question == LENGTH.text, "in the words the reviewer saw"


def test_work_the_sources_exclude_is_recorded_and_blocked_if_a_story_implements_it() -> None:
    draft = _draft(
        _story("S1", _criterion("A user can book a slot.", BOOK)),
        _story("S2", _criterion("A society can book weekly.", RECURRING), covers=("T2",)),
        statements=(
            _statement("T2", "exclusion", RECURRING),
            _statement("T3", "proposal", CANCEL_RULE),
        ),
    )

    proposal = _propose(draft)

    assert [(n.kind, n.evidence[0].block_id) for n in proposal.out_of_scope] == [
        ("excluded", BLOCK_IDS["B3"]),
        ("suggested", BLOCK_IDS["B4"]),
    ]
    blocked = _decision(proposal, "X-T2")
    assert (blocked.kind, blocked.status, blocked.affects) == ("conflict", "open", ("S2",))
    assert "rule out" in blocked.question


def test_an_open_question_nobody_asked_becomes_a_decision_without_inventing_scope() -> None:
    draft = _draft(
        _story("S1", _criterion("A user can book a slot.", BOOK)),
        statements=(_statement("T2", "open_question", CANCEL_RULE),),
    )

    decision = _decision(_propose(draft), "T2")

    assert (decision.kind, decision.status, decision.affects) == ("missing_decision", "open", ())


def test_a_question_may_only_block_stories_of_its_own_draft() -> None:
    with pytest.raises(ValidationError, match="affects E1, S9"):
        _draft(_story("S1"), questions=(_question(BOOK, affects=("S1", "E1", "S9")),))


def test_the_agent_prompt_asks_which_stories_each_question_blocks() -> None:
    assert PROMPT_SCHEMAS["draft-v4"] == "draft-backlog.v3"
    draft = _draft(_story("S1", _criterion("Book.", BOOK)), questions=(_question(BOOK),))
    patch = DraftPatchV3.model_validate(
        {
            "statements": [],
            "items": [],
            "questions": [_question(BOOK, affects=("S1",)) | {"replaces": 1}],
        }
    )

    patched = apply_patch(draft, patch)

    assert isinstance(patched, DraftBacklogV3)
    assert [q.affects for q in patched.questions] == [["S1"]]


def test_a_draft_v4_repair_returns_a_patch_with_the_blocked_stories() -> None:
    blocks = [SourceBlockInput(label, "source", text) for label, (_, text) in TEXTS.items()]
    unasked = _draft(
        _story("S1", _criterion("Book.", BOOK)),
        statements=(
            _statement("T2", "conflict", FOUR_HOURS, THREE_HOURS),
            _statement("T3", "context", RECURRING, CANCEL_RULE),
        ),
    )
    patch = {
        "statements": [],
        "items": [],
        "questions": [_question(FOUR_HOURS, THREE_HOURS, affects=("S1",)) | {"replaces": None}],
    }
    provider = ScriptedProvider([_result(unasked.model_dump_json()), _result(json.dumps(patch))])

    outcome = draft_single_pass(provider, blocks, max_output_tokens=100, prompt="draft-v4")

    assert isinstance(outcome.draft, DraftBacklogV3)
    assert (outcome.repair, outcome.repaired, outcome.check_problems) == ("targeted", True, ())
    assert outcome.draft.questions[0].affects == ["S1"]
    assert "affects" in json.dumps(provider.requests[0].output_schema)
    assert "affects" in json.dumps(provider.requests[1].output_schema)


def _result(text: str) -> ModelResult:
    return ModelResult(
        provider="test",
        model_id="test-model",
        turn=ModelTurn(({"type": "model_output", "text": text},)),
        text=text,
        tool_calls=(),
        finish_reason="completed",
        usage=Usage(input_tokens=10, output_tokens=10, total_tokens=20),
        latency_ms=1,
    )


ANSWERED_LENGTH = replace(
    LENGTH, status=QuestionStatus.ANSWERED, answer="Three hours.", answer_label="A1"
)
THREE = {"block_id": "A1", "quote": "Three hours."}


@pytest.mark.parametrize("asked_again", [True, False])
def test_a_conflict_the_reviewer_answered_is_not_stored_again_as_open(asked_again: bool) -> None:
    draft = _draft(
        _story("S1", _criterion("A booking lasts at most 3 hours.", THREE, THREE_HOURS)),
        statements=(
            _statement("T2", "conflict", FOUR_HOURS, THREE_HOURS)
            | {"summary": "The maximum booking length is 4 hours in the brief, 3 in the meeting."},
        ),
        questions=(_question(FOUR_HOURS, THREE_HOURS),) if asked_again else (),
    )

    proposal = _propose(draft, ANSWERED_LENGTH)

    (decision,) = proposal.decisions
    assert (decision.key, decision.status, decision.answer) == ("A1", "answered", "Three hours.")
    assert decision.affects == ("S1",)


def test_a_question_citing_the_answer_it_repeats_is_not_stored_again() -> None:
    draft = _draft(
        _story("S1", _criterion("A booking lasts at most 3 hours.", THREE)),
        questions=(_question(THREE) | {"subject": "Something else"},),
    )

    assert [d.key for d in _propose(draft, ANSWERED_LENGTH).decisions] == ["A1"]


@pytest.mark.parametrize(
    "question",
    [
        _question(FOUR_HOURS) | {"subject": "Group bookings"},
        _question(FOUR_HOURS, CANCEL_RULE),
    ],
    ids=["another subject in the same paragraph", "a paragraph the reviewer was not asked about"],
)
def test_a_new_point_near_an_answered_one_stays_open(question: dict[str, Any]) -> None:
    draft = _draft(
        _story("S1", _criterion("A booking lasts at most 3 hours.", THREE)),
        questions=(question,),
    )

    proposal = _propose(draft, ANSWERED_LENGTH)

    assert _decision(proposal, "Q1").status == "open"
    assert _decision(proposal, "A1").status == "answered"


def test_a_criterion_stating_one_side_without_the_answer_is_still_withheld() -> None:
    draft = _draft(
        _story(
            "S1",
            _criterion("A booking lasts at most 3 hours.", THREE),
            _criterion("A booking lasts at most 4 hours.", FOUR_HOURS),
        ),
        statements=(_statement("T2", "conflict", FOUR_HOURS, THREE_HOURS),),
        questions=(_question(FOUR_HOURS, THREE_HOURS),),
    )

    proposal = _propose(draft, ANSWERED_LENGTH)

    assert [c.text for c in _item(proposal, "S1").criteria] == ["A booking lasts at most 3 hours."]


def test_paragraphs_filed_only_as_context_are_set_aside_for_the_reviewer() -> None:
    context = _statement("T2", "context", CANCEL_RULE, BOOK) | {"summary": "Dana on cancelling."}
    draft = _draft(
        _story("S1", _criterion("A user can book a slot.", BOOK)),
        statements=(
            context,
            _statement("T3", "context", CANCEL_RULE),
            _statement("T4", "context", THREE_HOURS),
            _statement("T5", "conflict", THREE_HOURS, FOUR_HOURS),
        ),
        questions=(_question(THREE_HOURS, FOUR_HOURS),),
    )

    (note,) = _propose(draft).set_aside

    assert note.summary == "Dana on cancelling."
    assert [e.block_id for e in note.evidence] == [BLOCK_IDS["B4"]], (
        "B1 is cited by a criterion, B2 by a question and a conflict, and B4 is listed once"
    )


def test_a_set_aside_quote_that_does_not_resolve_is_dropped() -> None:
    draft = _draft(
        _story("S1", _criterion("A user can book a slot.", BOOK)),
        statements=(_statement("T2", "context", {"block_id": "B4", "quote": "invented"}),),
    )

    assert _propose(draft).set_aside == ()


def test_a_heading_filed_as_context_is_not_set_aside() -> None:
    heading = Passage(SourceBlockId(UUID(int=20)), BRIEF, "brief", 9, "## Background")
    draft = _draft(
        _story("S1", _criterion("A user can book a slot.", BOOK)),
        statements=(_statement("T2", "context", {"block_id": "B9", "quote": "Background"}),),
    )

    assert to_proposal(RUN, draft, {**PASSAGES, "B9": heading}, ()).set_aside == ()
