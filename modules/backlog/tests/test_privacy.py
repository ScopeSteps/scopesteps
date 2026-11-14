"""The personal-data check: what it finds, what it leaves alone, and where it looks."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from scopesteps.backlog.domain.ids import CriterionId, ItemId, TaskId
from scopesteps.backlog.domain.privacy import find_personal_data, privacy_flags, unsettled
from scopesteps.backlog.domain.version import Criterion, Evidence, Item, KeptFlag, Task
from scopesteps.identity.client import UserId

QUOTED = Evidence(UUID(int=1), UUID(int=2), "Ring Dana on 07700 900123 about it")
CRITERION = Criterion(CriterionId(UUID(int=10)), "A student books one slot.", "source", (QUOTED,))
STORY = Item(
    ItemId(UUID(int=20)),
    "story",
    ItemId(UUID(int=19)),
    "Book a room",
    "Questions go to rooms@college.example.",
    criteria=(CRITERION,),
    tasks=(Task(TaskId(UUID(int=30)), "Show card 4111 1111 1111 1111 in tests", "person"),),
)


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("Email support@club.example when it fails", [("email", "support@club.example")]),
        ("Sam.Okafor@uni.example.ac.uk wrote", [("email", "Sam.Okafor@uni.example.ac.uk")]),
        (
            "Call +44 7700 900123 or (555) 123-4567.",
            [
                ("phone", "+44 7700 900123"),
                ("phone", "(555) 123-4567"),
            ],
        ),
        ("mobile 07700900123, then", [("phone", "07700900123")]),
        ("Card 4111 1111 1111 1111 was charged", [("card", "4111 1111 1111 1111")]),
        ("loyalty number 123456789012 shows", [("number", "123456789012")]),
        ("Bookings last up to 2 hours from 2026-11-13.", []),
        ("Pay 1 250 000 points a year", []),
        ("Release 1.2.3 on server 10.0.0.12.", []),
        ("Up to 30 epics and 200 stories, order 12345678", []),
        ("Open 09:00-17:00 from 2026-11-13 to 2026-12-01", []),
    ],
)
def test_finds_contact_and_card_numbers_but_not_dates_amounts_or_versions(
    text: str, found: list[tuple[str, str]]
) -> None:
    assert find_personal_data(text) == found


def test_flags_the_title_description_criteria_quotes_and_tasks_in_plain_words() -> None:
    flags = privacy_flags([STORY])

    assert [(f.place, f.kind, f.reason) for f in flags] == [
        ("description", "email", "An email address in the description"),
        ("quote", "phone", "A phone number in a quote an acceptance criterion cites"),
        ("task", "card", "A payment card number in a task"),
    ]
    assert flags[1].criterion_id == CRITERION.id
    assert flags[2].task_id == TaskId(UUID(int=30))


def test_a_rejected_suggestion_is_not_checked_since_approval_leaves_it_out() -> None:
    rejected = Criterion(
        CriterionId(UUID(int=11)), "Text 07700 900123", "proposed", suggestion="rejected"
    )
    story = replace(STORY, description="", criteria=(rejected,), tasks=())

    assert privacy_flags([story]) == []


def test_a_flag_keeps_its_id_while_its_value_stays_and_a_kept_one_is_settled() -> None:
    (first, *_) = privacy_flags([STORY])
    reworded = replace(STORY, title="Book a study room")
    moved = replace(STORY, description="Write to helpdesk@college.example.")
    kept = KeptFlag(first.id, UserId(UUID(int=5)), datetime(2026, 11, 13, tzinfo=UTC))

    assert privacy_flags([reworded])[0].id == first.id
    assert privacy_flags([moved])[0].id != first.id
    assert first not in unsettled(privacy_flags([STORY]), [kept])
    assert len(unsettled(privacy_flags([STORY]), [kept])) == 2
