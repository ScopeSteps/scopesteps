from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from itertools import count
from uuid import UUID

import pytest

from scopesteps.backlog.domain.change import (
    ChangeProposal,
    NewItem,
    TaskRewrite,
    build_change_candidate,
    change_problems,
)
from scopesteps.backlog.domain.change import (
    ItemEdit as ChangeItemEdit,
)
from scopesteps.backlog.domain.editing import InvalidItemEditError, ItemEdit, TaskEdit, apply_edit
from scopesteps.backlog.domain.history import compare_items
from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, ItemId, TaskId
from scopesteps.backlog.domain.tasks import task_flag, task_scope, with_suggested_tasks
from scopesteps.backlog.domain.version import (
    MAX_TASKS_PER_STORY,
    BacklogVersion,
    Criterion,
    Item,
    ScopeNote,
    Task,
    VersionState,
    content_hash,
    find_blockers,
)
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
EDITOR = UserId(UUID(int=7))
EPIC = Item(ItemId(UUID(int=20)), "epic", None, "Room booking", "Booking rooms.")
OVERLAP = Criterion(
    CriterionId(UUID(int=10)),
    "A booking that overlaps another booking is refused.",
    "source",
)
STORY = Item(
    ItemId(UUID(int=21)),
    "story",
    EPIC.id,
    "Book a one-off slot",
    "As a student, I want to book a study room for one slot.",
    criteria=(OVERLAP,),
)
SUGGESTED = Task(TaskId(UUID(int=40)), "Design the booking screen", "suggested", "pending")
WRITTEN = Task(TaskId(UUID(int=41)), "Build the overlap check", "person", edited_by=EDITOR)
RECURRING = ScopeNote("excluded", "Recurring bookings are out of scope for release one.")


def _ids(start: int = 100) -> Callable[[], UUID]:
    numbers = count(start)
    return lambda: UUID(int=next(numbers))


def _edit(story: Item, *tasks: TaskEdit) -> tuple[Item, str]:
    edited, summary = apply_edit(
        story, ItemEdit(tasks=tasks), editor=EDITOR, now=NOW, new_id=_ids()
    )
    return edited, summary.describe()


def test_a_person_adds_a_task_with_a_new_id_and_their_name() -> None:
    edited, said = _edit(STORY, TaskEdit(None, "  Write tests   for the overlap check "))

    (task,) = edited.tasks
    assert (task.id, task.title, task.origin, task.edited_by) == (
        TaskId(UUID(int=100)),
        "Write tests for the overlap check",
        "person",
        EDITOR,
    )
    assert edited.human_edited
    assert said == "added 1 task"


def test_tasks_are_reordered_reworded_and_deleted_by_their_stable_ids() -> None:
    story = replace(STORY, tasks=(SUGGESTED, WRITTEN))

    edited, said = _edit(story, TaskEdit(WRITTEN.id, "Build the overlap rule"))

    assert [(t.id, t.title) for t in edited.tasks] == [(WRITTEN.id, "Build the overlap rule")]
    assert said == "edited 1 task, removed 1 task"

    moved, said = _edit(
        story, TaskEdit(WRITTEN.id, WRITTEN.title), TaskEdit(SUGGESTED.id, SUGGESTED.title)
    )

    assert [t.id for t in moved.tasks] == [WRITTEN.id, SUGGESTED.id]
    assert said == "reordered the tasks"


def test_accepting_or_rewording_a_suggested_task_accepts_it_and_keeps_its_label() -> None:
    story = replace(STORY, tasks=(SUGGESTED,))

    accepted, said = _edit(story, TaskEdit(SUGGESTED.id, SUGGESTED.title, accept=True))
    reworded, _ = _edit(story, TaskEdit(SUGGESTED.id, "Design the slot picker"))

    assert (accepted.tasks[0].origin, accepted.tasks[0].suggestion) == ("suggested", "accepted")
    assert accepted.tasks[0].edited_by is None
    assert not accepted.human_edited, "accepting changes no content"
    assert said == "accepted 1 suggested task"
    assert (reworded.tasks[0].suggestion, reworded.tasks[0].edited_by) == ("accepted", EDITOR)


@pytest.mark.parametrize(
    ("story", "edits", "problem"),
    [
        (EPIC, (TaskEdit(None, "Plan the epic"),), "only a story has tasks"),
        (STORY, (TaskEdit(None, " "),), "task 1 needs a title of 1 to 200 characters"),
        (STORY, (TaskEdit(None, "x" * 201),), "task 1 needs a title of 1 to 200 characters"),
        (STORY, (TaskEdit(TaskId(UUID(int=99)), "Ghost"),), "is not on this story"),
        (STORY, (TaskEdit(None, "New", accept=True),), "is new, so it is not a suggested task"),
        (
            replace(STORY, tasks=(WRITTEN,)),
            (TaskEdit(WRITTEN.id, WRITTEN.title, accept=True),),
            "written by a person, so it is not a suggestion",
        ),
        (
            replace(STORY, tasks=(WRITTEN,)),
            (TaskEdit(WRITTEN.id, "A"), TaskEdit(WRITTEN.id, "B")),
            "is listed more than once",
        ),
        (
            STORY,
            tuple(TaskEdit(None, f"Step {n}") for n in range(MAX_TASKS_PER_STORY + 1)),
            f"a story has at most {MAX_TASKS_PER_STORY} tasks",
        ),
    ],
)
def test_a_task_edit_that_breaks_a_rule_changes_nothing(
    story: Item, edits: tuple[TaskEdit, ...], problem: str
) -> None:
    with pytest.raises(InvalidItemEditError) as refused:
        _edit(story, *edits)

    assert problem in str(refused.value)


def test_a_pending_suggested_task_blocks_approval_until_reviewed() -> None:
    story = replace(STORY, tasks=(SUGGESTED, WRITTEN))

    (blocker,) = find_blockers((EPIC, story), ())
    accepted = replace(story, tasks=(replace(SUGGESTED, suggestion="accepted"), WRITTEN))

    assert (blocker.code, blocker.item_id, blocker.task_id) == (
        "suggested_task",
        STORY.id,
        SUGGESTED.id,
    )
    assert find_blockers((EPIC, accepted), ()) == ()


def test_content_without_tasks_hashes_as_before_and_tasks_change_the_hash() -> None:
    plain = content_hash((EPIC, STORY), (), ())

    assert plain == content_hash((EPIC, replace(STORY, tasks=())), (), ())
    assert plain != content_hash((EPIC, replace(STORY, tasks=(WRITTEN,))), (), ())


CANCEL = Item(
    ItemId(UUID(int=22)),
    "story",
    EPIC.id,
    "Cancel a booking",
    "Coaches and students cancel their bookings; the batteries in the door locks are not ours.",
)
SCOPE = task_scope((EPIC, STORY, CANCEL), [RECURRING])


def _task(title: str) -> Task:
    return Task(TaskId(UUID(int=50)), title, "suggested", "pending")


@pytest.mark.parametrize(
    "title",
    [
        "Design the booking screen",
        "Build the overlap check",
        "Write tests for booking a slot",
        # Words another story uses are not new work, plural or singular.
        "Add a cancel button for a coach",
        "Check the battery of each door lock",
        # How work is done, whatever the stories say.
        "Implement automatic sorting of rooms in the system",
        # Everyday words beside the backlog's own are fine.
        "Ensure the slot picker shows every option",
    ],
)
def test_a_task_that_says_how_to_do_the_backlog_is_not_flagged(title: str) -> None:
    assert task_flag(_task(title), SCOPE) is None


def test_a_task_naming_excluded_work_is_flagged_with_the_note_it_matches() -> None:
    flag = task_flag(_task("Add recurring booking support"), SCOPE)

    assert flag is not None
    assert flag.code == "out_of_scope_work"
    assert "recurring" in flag.message
    assert RECURRING.summary in flag.message


def test_a_word_the_backlog_uses_is_not_excluded_work_even_if_a_note_uses_it() -> None:
    scope = task_scope((EPIC, STORY), [ScopeNote("excluded", "Room booking by text is out.")])

    assert task_flag(_task("Design the room booking screen"), scope) is None


def test_a_task_naming_nothing_the_backlog_mentions_is_flagged_in_plain_words() -> None:
    flag = task_flag(_task("Integrate with Outlook calendar"), SCOPE)

    assert flag is not None
    assert flag.code == "new_work"
    assert "“calendar” or “outlook”" in flag.message


def test_new_suggestions_replace_unreviewed_ones_and_skip_repeats() -> None:
    story = replace(STORY, tasks=(SUGGESTED, WRITTEN))

    updated, added = with_suggested_tasks(
        story, ["build the OVERLAP check", "Write tests", " ", "Write tests"], _ids()
    )

    assert [(t.title, t.origin, t.suggestion) for t in updated.tasks] == [
        ("Build the overlap check", "person", None),
        ("Write tests", "suggested", "pending"),
    ]
    assert added == 1


def test_suggestions_stop_at_the_task_limit() -> None:
    full = tuple(
        Task(TaskId(UUID(int=200 + n)), f"Step {n}", "person")
        for n in range(MAX_TASKS_PER_STORY - 1)
    )

    updated, added = with_suggested_tasks(replace(STORY, tasks=full), ["One", "Two"], _ids())

    assert (len(updated.tasks), added) == (MAX_TASKS_PER_STORY, 1)


def _baseline(*items: Item) -> BacklogVersion:
    return BacklogVersion(
        id=BacklogVersionId(UUID(int=1)),
        project_id=ProjectId(UUID(int=2)),
        base_version_id=None,
        revision=1,
        state=VersionState.APPROVED,
        content_hash=content_hash(items, (), ()),
        run_id=None,
        source_version_ids=(),
        items=items,
        decisions=(),
        out_of_scope=(),
        created_by=EDITOR,
        created_at=NOW,
    )


def _proposal(
    base: BacklogVersion,
    *,
    edited: tuple[ChangeItemEdit, ...] = (),
    added: tuple[NewItem, ...] = (),
) -> ChangeProposal:
    return ChangeProposal(
        project_id=base.project_id,
        run_id=UUID(int=3),
        created_by=EDITOR,
        base_version_id=base.id,
        base_content_hash=base.content_hash,
        source_version_ids=(),
        edited=edited,
        added=added,
    )


def test_a_change_adds_rewords_and_removes_tasks_by_their_stable_ids() -> None:
    base = _baseline(
        EPIC, replace(STORY, tasks=(replace(SUGGESTED, suggestion="accepted"), WRITTEN))
    )
    proposal = _proposal(
        base,
        edited=(
            ChangeItemEdit(
                STORY.id,
                added_tasks=("Write tests for the overlap check",),
                changed_tasks=(TaskRewrite(WRITTEN.id, "Build the overlap rule"),),
                removed_tasks=(SUGGESTED.id,),
            ),
        ),
        added=(
            NewItem("S2", "story", EPIC.id, "Cancel a booking", "", tasks=("Add a cancel button",)),
        ),
    )

    built = build_change_candidate(base, proposal, new_id=_ids(), now=NOW).version

    story = next(item for item in built.items if item.id == STORY.id)
    new_story = next(item for item in built.items if item.title == "Cancel a booking")
    assert [(t.id, t.title, t.origin) for t in story.tasks] == [
        (WRITTEN.id, "Build the overlap rule", "person"),
        (story.tasks[1].id, "Write tests for the overlap check", "suggested"),
    ]
    assert [(t.title, t.suggestion) for t in new_story.tasks] == [
        ("Add a cancel button", "accepted")
    ]
    (change,) = [c for c in compare_items(base.items, built.items) if c.item_id == STORY.id]
    assert sorted((t.kind, t.task_id) for t in change.tasks) == sorted(
        [("added", story.tasks[1].id), ("modified", WRITTEN.id), ("removed", SUGGESTED.id)]
    )


@pytest.mark.parametrize(
    ("edit", "problem"),
    [
        (ChangeItemEdit(EPIC.id, added_tasks=("Plan",)), "only a story has tasks"),
        (ChangeItemEdit(STORY.id, removed_tasks=(TaskId(UUID(int=99)),)), "is not on item"),
        (ChangeItemEdit(STORY.id, added_tasks=("",)), "needs task titles"),
        (
            ChangeItemEdit(
                STORY.id, added_tasks=tuple(f"Step {n}" for n in range(MAX_TASKS_PER_STORY))
            ),
            f"would have more than {MAX_TASKS_PER_STORY} tasks",
        ),
    ],
)
def test_a_change_with_a_wrong_task_operation_is_refused(
    edit: ChangeItemEdit, problem: str
) -> None:
    base = _baseline(EPIC, replace(STORY, tasks=(WRITTEN,)))

    problems = change_problems(base, _proposal(base, edited=(edit,)))

    assert any(problem in p for p in problems), problems
