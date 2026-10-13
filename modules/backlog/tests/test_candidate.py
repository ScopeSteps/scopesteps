from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from scopesteps.backlog.domain.candidate import (
    CandidateProposal,
    CandidateRejectedError,
    ProposedCriterion,
    ProposedDecision,
    ProposedItem,
    build_candidate,
    structural_problems,
)
from scopesteps.backlog.domain.version import Evidence, ScopeNote
from scopesteps.identity.client import UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
REVIEWER = UserId(UUID(int=7))
VERSION = UUID(int=1)
PASSAGE = Evidence(VERSION, UUID(int=2), "book an individual one-off slot")

EPIC = ProposedItem("E1", "epic", None, "Room booking", "Booking rooms.")
SOURCED = ProposedCriterion("A user can book a free room.", proposed=False, evidence=(PASSAGE,))
PROPOSED = ProposedCriterion("The user sees a confirmation.", proposed=True)
STORY = ProposedItem(
    "S1",
    "story",
    "E1",
    "Book a room",
    "As a student, I want to book a room, so that I can study.",
    criteria=(SOURCED,),
)
LENGTH = ProposedDecision(
    key="Q1",
    kind="conflict",
    status="open",
    subject="Maximum booking length",
    question="Is the maximum three or four hours?",
    why_it_matters="The brief and the transcript disagree.",
    affects=("S1",),
)
CANCELLATION = ProposedDecision(
    key="A1",
    kind="missing_decision",
    status="answered",
    subject="Cancellation",
    question="How late may a user cancel?",
    why_it_matters="No rule is agreed.",
    answer="Up to one hour before the start.",
    decided_by=REVIEWER,
    decided_at=NOW,
)


def _proposal(
    *items: ProposedItem, decisions: tuple[ProposedDecision, ...] = ()
) -> CandidateProposal:
    return CandidateProposal(
        project_id=ProjectId(UUID(int=9)),
        run_id=UUID(int=3),
        created_by=REVIEWER,
        source_version_ids=(VERSION,),
        items=items or (EPIC, STORY),
        decisions=decisions,
        out_of_scope=(ScopeNote("excluded", "No recurring bookings in release one."),),
    )


def _story(ref: str, **changes: object) -> ProposedItem:
    return replace(STORY, ref=ref, **changes)  # type: ignore[arg-type]  # test helper


@pytest.mark.parametrize(
    ("proposal", "expected"),
    [
        (_proposal(EPIC, STORY, STORY), "item ref S1 is used 2 times"),
        (_proposal(EPIC, _story("S1", parent_ref="E9")), "story S1 has no epic 'E9'"),
        (_proposal(EPIC, _story("S1", parent_ref=None)), "story S1 has no epic None"),
        (_proposal(EPIC, STORY, _story("S2", parent_ref="S1")), "story S2 has no epic 'S1'"),
        (_proposal(EPIC, replace(EPIC, ref="E2", parent_ref="E1")), "epic E2 cannot have a parent"),
        (
            _proposal(*(replace(EPIC, ref=f"E{n}") for n in range(1, 4))),
            "3 epics exceed the limit of 2",
        ),
        (
            _proposal(EPIC, *(_story(f"S{n}") for n in range(1, 10))),
            "9 stories exceed the limit of 8",
        ),
        (_proposal(EPIC, _story("S1", title="  ")), "S1 needs a title"),
        (
            _proposal(decisions=(replace(LENGTH, affects=("S7",)),)),
            "decision Q1 affects unknown items S7",
        ),
        (_proposal(decisions=(LENGTH, LENGTH)), "decision Q1 is given 2 times"),
        (
            _proposal(decisions=(replace(CANCELLATION, answer=None),)),
            "decision A1 must have an answer exactly when answered",
        ),
        (
            _proposal(decisions=(replace(CANCELLATION, decided_by=None),)),
            "decision A1 does not record who decided it",
        ),
        (
            _proposal(
                EPIC,
                _story("S1", criteria=(replace(SOURCED, confirmed_by=("A1",)),)),
                decisions=(replace(CANCELLATION, status="skipped", answer=None),),
            ),
            "S1 is confirmed by A1, which no reviewer answered",
        ),
    ],
)
def test_an_unsound_proposal_is_rejected_with_the_reason(
    proposal: CandidateProposal, expected: str
) -> None:
    problems = structural_problems(proposal)

    assert any(expected in problem for problem in problems), problems
    with pytest.raises(CandidateRejectedError) as rejected:
        build_candidate(proposal, new_id=new_id, now=NOW)
    assert rejected.value.code == "CANDIDATE_REJECTED"
    assert rejected.value.details["problems"] == problems


def test_a_backlog_smaller_than_the_ceilings_is_sound() -> None:
    proposal = _proposal(EPIC, STORY)

    assert structural_problems(proposal) == []


def test_a_candidate_becomes_a_first_revision_draft_with_stable_ids() -> None:
    version = build_candidate(_proposal(decisions=(LENGTH,)), new_id=new_id, now=NOW)

    epic, story = version.items
    assert (version.state.value, version.revision, version.base_version_id) == ("draft", 1, None)
    assert story.parent_id == epic.id
    assert version.decisions[0].affected_item_ids == (story.id,)
    assert len({epic.id, story.id, story.criteria[0].id, version.decisions[0].id}) == 4
    assert len(version.content_hash) == 64


@pytest.mark.parametrize(
    ("criterion", "origin"),
    [
        (SOURCED, "source"),
        (replace(SOURCED, confirmed_by=("A1",)), "human"),
        (ProposedCriterion("Reviewer's rule.", proposed=False, confirmed_by=("A1",)), "human"),
        (PROPOSED, "proposed"),
        # A detail the agent added stays proposed even when it points at a passage.
        (replace(SOURCED, proposed=True), "proposed"),
        # A claim that lost its only citation is no longer sourced.
        (replace(SOURCED, evidence=()), "proposed"),
    ],
)
def test_a_criterion_is_only_as_strong_as_its_support(
    criterion: ProposedCriterion, origin: str
) -> None:
    proposal = _proposal(EPIC, _story("S1", criteria=(criterion,)), decisions=(CANCELLATION,))

    version = build_candidate(proposal, new_id=new_id, now=NOW)

    assert version.items[1].criteria[0].origin == origin


def test_unresolved_decisions_and_proposed_criteria_block_the_items_they_affect() -> None:
    skipped = replace(
        CANCELLATION, key="U1", status="skipped", answer=None, affects=("S2",), subject="No-shows"
    )
    unlinked = replace(
        LENGTH, key="Q2", kind="missing_decision", affects=(), subject="Opening hours"
    )
    proposal = _proposal(
        EPIC,
        _story("S1", criteria=(SOURCED, PROPOSED)),
        _story("S2"),
        _story("S3", criteria=(replace(SOURCED, confirmed_by=("A1",)),)),
        decisions=(LENGTH, skipped, unlinked, CANCELLATION),
    )

    version = build_candidate(proposal, new_id=new_id, now=NOW)

    _, first, second, third = version.items
    blockers = {(b.code, b.item_id): b for b in version.blockers()}
    assert set(blockers) == {
        ("unresolved_conflict", first.id),
        ("proposed_criterion", first.id),
        ("open_decision", second.id),
        ("open_decision", None),
    }
    assert blockers["proposed_criterion", first.id].criterion_id == first.criteria[1].id
    assert (
        blockers["open_decision", second.id].message
        == "The reviewer skipped this decision: No-shows"
    )
    assert third.id not in {b.item_id for b in version.blockers()}, "an answer blocks nothing"


def test_the_content_hash_changes_with_the_content_only() -> None:
    ids = iter(UUID(int=n) for n in range(100, 200))
    same_ids = iter(UUID(int=n) for n in range(100, 200))
    other_ids = iter(UUID(int=n) for n in range(100, 200))
    edited = _proposal(EPIC, _story("S1", title="Reserve a room"))

    first = build_candidate(_proposal(), new_id=lambda: next(ids), now=NOW)
    again = build_candidate(_proposal(), new_id=lambda: next(same_ids), now=NOW.replace(hour=11))
    changed = build_candidate(edited, new_id=lambda: next(other_ids), now=NOW)

    assert first.content_hash == again.content_hash
    assert first.content_hash != changed.content_hash
