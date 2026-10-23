from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from scopesteps.backlog.domain.editing import (
    CriterionEdit,
    DecisionAlreadyAnsweredError,
    InvalidDecisionAnswerError,
    InvalidItemEditError,
    ItemEdit,
    NotAScopeDecisionError,
    answer_decision,
    apply_edit,
    change_clarification_answer,
    settle_scope_decision,
)
from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, DecisionId, ItemId
from scopesteps.backlog.domain.review import CheckCode, ProblemRef, review_checks
from scopesteps.backlog.domain.version import (
    BacklogVersion,
    Criterion,
    Decision,
    Evidence,
    Item,
    VersionState,
    approved_content,
    content_hash,
    find_blockers,
)
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
EDITOR = UserId(UUID(int=7))
SOURCE_VERSION = UUID(int=1)
PASSAGE = Evidence(SOURCE_VERSION, UUID(int=2))
SOURCED = Criterion(CriterionId(UUID(int=10)), "A user can book a free room.", "source", (PASSAGE,))
SUGGESTED = Criterion(
    CriterionId(UUID(int=11)), "The user sees a confirmation.", "proposed", suggestion="pending"
)
EPIC = Item(ItemId(UUID(int=20)), "epic", None, "Room booking", "Booking rooms.")
STORY = Item(
    ItemId(UUID(int=21)),
    "story",
    EPIC.id,
    "Book a room",
    "As a student, I want to book a room.",
    criteria=(SOURCED, SUGGESTED),
)
OPEN = Decision(
    DecisionId(UUID(int=30)),
    "conflict",
    "skipped",
    "Maximum booking length",
    "Three or four hours?",
    "The sources disagree.",
    affected_item_ids=(STORY.id,),
)


class Ids:
    def __init__(self) -> None:
        self.next = 100

    def __call__(self) -> UUID:
        self.next += 1
        return UUID(int=self.next)


def _edit(edit: ItemEdit, item: Item = STORY) -> tuple[Item, str]:
    edited, summary = apply_edit(item, edit, editor=EDITOR, now=NOW, new_id=Ids())
    return edited, summary.describe()


def _keep(criterion: Criterion, **changes: object) -> CriterionEdit:
    return replace(CriterionEdit(criterion.id, criterion.text), **changes)  # type: ignore[arg-type]  # test helper


def _version(*items: Item, decisions: tuple[Decision, ...] = ()) -> BacklogVersion:
    items = items or (EPIC, STORY)
    return BacklogVersion(
        id=BacklogVersionId(UUID(int=40)),
        project_id=ProjectId(UUID(int=9)),
        base_version_id=None,
        revision=1,
        state=VersionState.DRAFT,
        content_hash=content_hash(items, decisions, ()),
        run_id=None,
        source_version_ids=(SOURCE_VERSION,),
        items=items,
        decisions=decisions,
        out_of_scope=(),
        created_by=EDITOR,
        created_at=NOW,
    )


def test_editing_text_keeps_every_id_and_records_who_edited() -> None:
    edited, described = _edit(
        ItemEdit(
            title="Book a study room",
            criteria=(
                _keep(SOURCED, text="A signed-in user can book a free room."),
                _keep(SUGGESTED),
            ),
        )
    )

    assert edited.id == STORY.id
    assert [c.id for c in edited.criteria] == [SOURCED.id, SUGGESTED.id]
    sourced = edited.criteria[0]
    assert (sourced.origin, sourced.evidence, sourced.edited_by) == ("source", (PASSAGE,), EDITOR)
    assert edited.criteria[1].edited_by is None, "untouched criteria keep their provenance"
    assert (edited.human_edited, edited.edited_by, edited.edited_at) == (True, EDITOR, NOW)
    assert described == "changed the title, edited 1 criterion"


def test_a_criterion_a_person_adds_gets_a_new_id_and_the_person_origin() -> None:
    edited, described = _edit(
        ItemEdit(
            criteria=(
                _keep(SOURCED),
                _keep(SUGGESTED),
                CriterionEdit(None, " Rooms show capacity. "),
            )
        )
    )

    added = edited.criteria[2]
    assert added.id not in {SOURCED.id, SUGGESTED.id}
    assert (added.text, added.origin, added.suggestion, added.edited_by) == (
        "Rooms show capacity.",
        "person",
        None,
        EDITOR,
    )
    assert described == "added 1 criterion"


@pytest.mark.parametrize(
    ("change", "status", "described"),
    [
        ({"suggestion": "accepted"}, "accepted", "accepted 1 suggestion"),
        ({"suggestion": "rejected"}, "rejected", "rejected 1 suggestion"),
        (
            {"text": "A confirmation names the room."},
            "accepted",
            "edited 1 criterion, accepted 1 suggestion",
        ),
        (
            {"text": "A confirmation names the room.", "suggestion": "rejected"},
            "rejected",
            "edited 1 criterion, rejected 1 suggestion",
        ),
    ],
)
def test_an_editor_settles_a_suggestion_by_accepting_rejecting_or_rewriting_it(
    change: dict[str, object], status: str, described: str
) -> None:
    edited, summary = _edit(ItemEdit(criteria=(_keep(SOURCED), _keep(SUGGESTED, **change))))

    assert edited.criteria[1].suggestion == status
    assert summary == described
    assert find_blockers((edited,), ()) == ()


def test_a_rejected_suggestion_can_be_reopened() -> None:
    rejected = replace(STORY, criteria=(SOURCED, replace(SUGGESTED, suggestion="rejected")))

    edited, described = _edit(
        ItemEdit(criteria=(_keep(SOURCED), _keep(SUGGESTED, suggestion="pending"))), rejected
    )

    assert edited.criteria[1].suggestion == "pending"
    assert described == "reopened 1 suggestion"
    assert not edited.human_edited, "reviewing a suggestion does not edit the content"


def test_a_criterion_left_out_is_removed() -> None:
    edited, described = _edit(ItemEdit(criteria=(_keep(SOURCED),)))

    assert edited.criteria == (SOURCED,)
    assert described == "removed 1 criterion"


def test_an_edit_that_changes_nothing_returns_the_item_unchanged() -> None:
    edited, described = _edit(
        ItemEdit(title=" Book a room ", criteria=(_keep(SOURCED), _keep(SUGGESTED)))
    )

    assert edited is STORY
    assert described == ""


@pytest.mark.parametrize(
    ("edit", "problem"),
    [
        (ItemEdit(title="   "), "a title is 1 to 200 characters"),
        (ItemEdit(title="x" * 201), "a title is 1 to 200 characters"),
        (
            ItemEdit(criteria=(CriterionEdit(CriterionId(UUID(int=99)), "x"),)),
            "is not on this item",
        ),
        (ItemEdit(criteria=(_keep(SOURCED), _keep(SOURCED))), "is listed more than once"),
        (ItemEdit(criteria=(_keep(SOURCED, text=" "),)), "criterion 1 has no text"),
        (ItemEdit(criteria=(_keep(SOURCED, suggestion="accepted"),)), "is not an agent suggestion"),
        (ItemEdit(criteria=(CriterionEdit(None, "x", "accepted"),)), "is new"),
    ],
)
def test_an_invalid_edit_is_refused_whole(edit: ItemEdit, problem: str) -> None:
    with pytest.raises(InvalidItemEditError) as refused:
        _edit(edit)

    assert refused.value.code == "ITEM_EDIT_INVALID"
    assert problem in refused.value.message


def test_only_a_pending_suggestion_blocks_its_item() -> None:
    def blockers(status: str) -> list[str]:
        item = replace(STORY, criteria=(SOURCED, replace(SUGGESTED, suggestion=status)))
        return [blocker.code for blocker in find_blockers((item,), ())]

    assert blockers("pending") == ["proposed_criterion"]
    assert blockers("accepted") == []
    assert blockers("rejected") == []


def test_rejecting_a_suggestion_changes_the_hash_and_approval_leaves_it_out() -> None:
    rejected = replace(STORY, criteria=(SOURCED, replace(SUGGESTED, suggestion="rejected")))
    without = replace(STORY, criteria=(SOURCED,))

    assert content_hash((rejected,), (), ()) != content_hash((STORY,), (), ())
    assert approved_content((rejected,)) == (without,)
    assert content_hash((rejected,), (), ()) == content_hash(approved_content((rejected,)), (), ())


def _results(
    version: BacklogVersion, citation_problems: list[str] | None = None
) -> dict[str, bool]:
    checks = review_checks(version, citation_problems or [])
    return {check.code.value: check.passed for check in checks}


def test_a_draft_passes_every_check_once_suggestions_and_decisions_are_settled() -> None:
    accepted = replace(STORY, criteria=(SOURCED, replace(SUGGESTED, suggestion="accepted")))

    assert _results(_version(EPIC, accepted)) == dict.fromkeys(
        [code.value for code in CheckCode], True
    )


def test_each_check_reports_its_own_problem() -> None:
    orphan = replace(STORY, parent_id=ItemId(UUID(int=99)))
    foreign = replace(SOURCED, evidence=(Evidence(UUID(int=5), UUID(int=6)),))
    checks = {
        check.code: check
        for check in review_checks(
            _version(EPIC, replace(orphan, criteria=(foreign, SUGGESTED)), decisions=(OPEN,)),
            ["block 6 is not a paragraph of source version 5"],
        )
    }

    assert not any(check.passed for check in checks.values())
    assert checks[CheckCode.STRUCTURE_VALID].problems == (f"story {STORY.id} belongs to no epic",)
    assert checks[CheckCode.CITATIONS_RESOLVE].problem_count == 2
    assert checks[CheckCode.SUGGESTIONS_REVIEWED].problems == (
        f"criterion {SUGGESTED.id} on item {STORY.id} is an unreviewed agent suggestion",
    )
    assert checks[CheckCode.DECISIONS_RESOLVED].problems == (f"decision {OPEN.id} is skipped",)
    assert checks[CheckCode.DECISIONS_RESOLVED].title == "No decision is open"
    # Each problem names what it is about, so a screen can show its title instead of the ids.
    assert checks[CheckCode.SUGGESTIONS_REVIEWED].refs == (
        ProblemRef(item_id=STORY.id, criterion_id=SUGGESTED.id),
    )
    assert checks[CheckCode.DECISIONS_RESOLVED].refs == (ProblemRef(decision_id=OPEN.id),)
    assert checks[CheckCode.STRUCTURE_VALID].refs == (ProblemRef(),)


def test_answering_a_skipped_decision_settles_it_and_keeps_line_breaks() -> None:
    answered = answer_decision(
        OPEN, "  Four hours.\r\nUnless the room is shared.  ", decided_by=EDITOR, now=NOW
    )

    assert answered.is_resolved
    assert answered.answer == "Four hours.\nUnless the room is shared."
    assert (answered.decided_by, answered.decided_at) == (EDITOR, NOW)
    assert (answered.id, answered.subject, answered.affected_item_ids) == (
        OPEN.id,
        OPEN.subject,
        OPEN.affected_item_ids,
    )


def test_an_answered_decision_cannot_be_answered_again() -> None:
    answered = answer_decision(OPEN, "Four hours.", decided_by=EDITOR, now=NOW)

    with pytest.raises(DecisionAlreadyAnsweredError):
        answer_decision(answered, "Three hours.", decided_by=EDITOR, now=NOW)


@pytest.mark.parametrize("answer", ["", " \n ", "x" * 2001, "Tab\there"])
def test_an_empty_long_or_unprintable_answer_is_refused(answer: str) -> None:
    with pytest.raises(InvalidDecisionAnswerError):
        answer_decision(OPEN, answer, decided_by=EDITOR, now=NOW)


def test_a_clarification_answer_can_be_changed_but_only_one_put_to_a_reviewer() -> None:
    asked = replace(OPEN, question_id=UUID(int=40))
    answered = answer_decision(asked, "Four hours.", decided_by=EDITOR, now=NOW)

    changed = change_clarification_answer(answered, " Three hours. ", decided_by=EDITOR, now=NOW)

    assert (changed.status, changed.answer, changed.decided_by) == (
        "answered",
        "Three hours.",
        EDITOR,
    )
    with pytest.raises(DecisionAlreadyAnsweredError):
        change_clarification_answer(OPEN, "Three hours.", decided_by=EDITOR, now=NOW)
    with pytest.raises(InvalidDecisionAnswerError):
        change_clarification_answer(answered, " ", decided_by=EDITOR, now=NOW)


REVERSAL = Decision(
    DecisionId(UUID(int=31)),
    "scope_reversal",
    "open",
    "Reverse: Recurring bookings are out of scope.",
    "Reverse the exclusion?",
    "Release one excluded them.",
    evidence=(PASSAGE,),
    affected_item_ids=(STORY.id,),
)


@pytest.mark.parametrize("outcome", ["reverse", "keep"])
def test_an_approver_settles_a_scope_decision_with_who_and_when(outcome: str) -> None:
    settled = settle_scope_decision(
        REVERSAL, "keep" if outcome == "keep" else "reverse", decided_by=EDITOR, now=NOW
    )

    assert settled.is_resolved
    assert (settled.scope_outcome, settled.decided_by, settled.decided_at) == (outcome, EDITOR, NOW)
    assert settled.evidence == REVERSAL.evidence, "it still cites what it reverses"
    assert find_blockers((STORY,), (settled,)) == find_blockers((STORY,), ())


def test_a_scope_decision_is_recorded_once_and_only_on_a_scope_reversal() -> None:
    settled = settle_scope_decision(REVERSAL, "reverse", decided_by=EDITOR, now=NOW)

    with pytest.raises(DecisionAlreadyAnsweredError):
        settle_scope_decision(settled, "keep", decided_by=EDITOR, now=NOW)
    with pytest.raises(NotAScopeDecisionError):
        settle_scope_decision(OPEN, "reverse", decided_by=EDITOR, now=NOW)
    assert REVERSAL.scope_outcome is None
