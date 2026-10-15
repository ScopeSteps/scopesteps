"""A change to an approved baseline, built into a candidate in review without touching the
baseline. Synthetic room-booking data."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from scopesteps.backlog.domain.candidate import ProposedCriterion
from scopesteps.backlog.domain.change import (
    ChangeDecision,
    ChangeProposal,
    ChangeRejectedError,
    CriterionEdit,
    ItemEdit,
    NewItem,
    build_change_candidate,
    change_problems,
)
from scopesteps.backlog.domain.history import compare_items
from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, ItemId
from scopesteps.backlog.domain.version import (
    BacklogVersion,
    Criterion,
    Evidence,
    Item,
    ScopeNote,
    VersionState,
    content_hash,
)
from scopesteps.identity.client import UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
PROJECT = ProjectId(UUID(int=1))
REVIEWER = UserId(UUID(int=7))
SOURCE = UUID(int=2)
REQUEST = UUID(int=3)
EXCLUSION = Evidence(SOURCE, UUID(int=4), "Recurring bookings are out of scope")
ASKED = Evidence(REQUEST, UUID(int=5), "weekly recurring bookings")

EPIC = Item(ItemId(UUID(int=10)), "epic", None, "Room booking", "Booking rooms.")
BOOK = Item(
    ItemId(UUID(int=11)),
    "story",
    EPIC.id,
    "Book a room",
    "As a student, I want to book a room.",
    criteria=(Criterion(CriterionId(UUID(int=21)), "A student books one slot.", "source"),),
    human_edited=True,
    edited_by=REVIEWER,
    edited_at=NOW,
)
CANCEL = Item(
    ItemId(UUID(int=12)),
    "story",
    EPIC.id,
    "Cancel a booking",
    "As a student, I want to cancel.",
    criteria=(
        Criterion(CriterionId(UUID(int=22)), "Cancel up to an hour before.", "source"),
        Criterion(CriterionId(UUID(int=23)), "A cancelled slot is free again.", "source"),
    ),
)
NOTES = (ScopeNote("excluded", "Recurring bookings", (EXCLUSION,)),)
BASE = BacklogVersion(
    id=BacklogVersionId(UUID(int=100)),
    project_id=PROJECT,
    base_version_id=None,
    revision=4,
    state=VersionState.APPROVED,
    content_hash=content_hash((EPIC, BOOK, CANCEL), (), NOTES),
    run_id=None,
    source_version_ids=(SOURCE,),
    items=(EPIC, BOOK, CANCEL),
    decisions=(),
    out_of_scope=NOTES,
    created_by=REVIEWER,
    created_at=NOW,
)
SERIES = NewItem(
    "N1",
    "story",
    EPIC.id,
    "Book a weekly series",
    "As a society, I want weekly bookings.",
    criteria=(ProposedCriterion("Same slot every week.", proposed=False, evidence=(ASKED,)),),
)
REVERSE = ChangeDecision(
    key="R1",
    kind="scope_reversal",
    status="open",
    subject="Reverse: Recurring bookings",
    question="Reverse the exclusion?",
    why_it_matters="Release one excluded it.",
    evidence=(EXCLUSION, ASKED),
    affects=("N1",),
)


def _proposal(**fields: Any) -> ChangeProposal:
    proposal = ChangeProposal(
        project_id=PROJECT,
        run_id=UUID(int=200),
        created_by=REVIEWER,
        base_version_id=BASE.id,
        base_content_hash=BASE.content_hash,
        source_version_ids=(SOURCE, REQUEST),
        added=(SERIES,),
        edited=(
            ItemEdit(
                CANCEL.id,
                changed_criteria=(
                    CriterionEdit(
                        CANCEL.criteria[0].id,
                        ProposedCriterion("Cancel one week or the series.", proposed=True),
                    ),
                ),
                removed_criteria=(CANCEL.criteria[1].id,),
            ),
        ),
        decisions=(REVERSE,),
        reversed_exclusions=(0,),
    )
    return replace(proposal, **fields)


def test_the_candidate_keeps_untouched_items_exactly_and_the_baseline_is_not_changed() -> None:
    before = replace(BASE)

    built = build_change_candidate(BASE, _proposal(), new_id=new_id, now=NOW)

    candidate = built.version
    assert before == BASE
    assert (candidate.state, candidate.base_version_id, candidate.revision) == (
        VersionState.IN_REVIEW,
        BASE.id,
        1,
    )
    assert candidate.items[:2] == (EPIC, BOOK), "unaffected items keep ids, content, provenance"
    assert candidate.out_of_scope == ()
    changes = compare_items(BASE.items, candidate.items)
    assert [(c.kind, c.item_id) for c in changes] == [
        ("modify_item", CANCEL.id),
        ("add_item", built.item_ids["N1"]),
    ]
    assert [(c.kind, c.criterion_id) for c in changes[0].criteria] == [
        ("modified", CANCEL.criteria[0].id),
        ("removed", CANCEL.criteria[1].id),
    ]
    edited = candidate.items[2].criteria[0]
    assert (edited.origin, edited.suggestion) == ("proposed", "pending")
    (decision,) = candidate.decisions
    assert decision.id == built.decision_ids["R1"]
    assert decision.affected_item_ids == (built.item_ids["N1"],)
    assert decision.evidence[0] == EXCLUSION
    assert any(b.code == "scope_decision" for b in candidate.blockers())


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        ({"base_content_hash": "0" * 64}, "does not have the content hash"),
        ({"added": (), "edited": (), "decisions": (), "reversed_exclusions": ()}, "nothing"),
        ({"removed": (ItemId(UUID(int=99)),)}, "is not in the baseline"),
        ({"removed": (CANCEL.id,)}, "is changed 2 times"),
        (
            {
                "edited": (ItemEdit(BOOK.id, removed_criteria=(CANCEL.criteria[0].id,)),),
            },
            "is not on item",
        ),
        ({"added": (replace(SERIES, parent="N9"),)}, "no new item has the ref N9"),
        ({"decisions": ()}, "without a scope decision"),
        ({"decisions": (replace(REVERSE, status="answered"),)}, "only an approver makes"),
        ({"removed": (EPIC.id,)}, "belongs to no epic"),
        (
            {"added": tuple(replace(SERIES, ref=f"N{n}") for n in range(1, 8))},
            "stories exceed the limit",
        ),
    ],
)
def test_an_unsound_change_is_refused(fields: dict[str, Any], problem: str) -> None:
    proposal = _proposal(**fields)

    found = change_problems(BASE, proposal)

    assert any(problem in p for p in found), found
    with pytest.raises(ChangeRejectedError):
        build_change_candidate(BASE, proposal, new_id=new_id, now=NOW)


def test_only_an_approved_baseline_can_be_changed() -> None:
    draft = replace(BASE, state=VersionState.DRAFT)

    assert change_problems(draft, _proposal()) == [f"version {BASE.id} is not an approved baseline"]
