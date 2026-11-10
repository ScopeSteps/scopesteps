"""Planning a publish and shaping what Jira receives, without a database or the network."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from cryptography.fernet import Fernet

from scopesteps.identity.client import UserId
from scopesteps.jira_integration.domain.connection import (
    IssueTypes,
    JiraConnection,
    JiraProject,
    check_token_expiry,
    normalise_project_key,
    normalise_site_url,
)
from scopesteps.jira_integration.domain.errors import JiraSiteInvalidError
from scopesteps.jira_integration.domain.plan import (
    ApprovedItem,
    IssueLink,
    issues_of,
    plan_publish,
)
from scopesteps.jira_integration.domain.publish import backoff
from scopesteps.jira_integration.infrastructure.crypto import FernetTokenCipher
from scopesteps.jira_integration.infrastructure.jira_http import description
from scopesteps.kernel.errors import InvalidInputError
from scopesteps.projects.client import ProjectId

EPIC = UUID("019a3a5e-0000-7000-8000-000000000a01")
STORY = UUID("019a3a5e-0000-7000-8000-000000000a02")
ORPHAN = UUID("019a3a5e-0000-7000-8000-000000000a03")
TASK = UUID("019a3a5e-0000-7000-8000-000000000a04")
GONE = UUID("019a3a5e-0000-7000-8000-000000000a05")
GONE_TASK = UUID("019a3a5e-0000-7000-8000-000000000a06")


def _items() -> list[ApprovedItem]:
    return [
        ApprovedItem(
            STORY,
            "story",
            EPIC,
            "Book a slot",
            "As a student.",
            ("One slot.",),
            (),
            (),
            ((TASK, "Build the check"),),
        ),
        ApprovedItem(EPIC, "epic", None, "Rooms", "Rooms.", (), (), (), ()),
        ApprovedItem(ORPHAN, "story", UUID(int=7), "Cancel", "", (), (), ("Who cancels?",), ()),
    ]


def _issues():
    return issues_of(_items(), lambda title: title.upper(), "https://app.test/projects/p/backlog")


def test_parents_come_first_and_a_story_without_its_epic_has_no_parent() -> None:
    issues = _issues()

    assert [(issue.kind, issue.item_id) for issue in issues] == [
        ("epic", EPIC),
        ("story", STORY),
        ("story", ORPHAN),
        ("task", TASK),
    ]
    assert [issue.parent_item_id for issue in issues] == [None, EPIC, None, STORY]
    assert issues[1].summary == "BOOK A SLOT"


def test_a_first_publish_creates_everything() -> None:
    plan = plan_publish(_issues(), {})

    assert [op.operation for op in plan.operations] == ["create"] * 4
    assert plan.counts()["story"].create == 2


def test_changed_closed_and_removed_items_update_and_close_and_the_rest_is_left_alone() -> None:
    issues = _issues()
    by_id = {issue.item_id: issue for issue in issues}
    links = {
        EPIC: IssueLink(EPIC, "epic", "R-1", "1", by_id[EPIC].fingerprint()),
        STORY: IssueLink(STORY, "story", "R-2", "2", "stale"),
        TASK: IssueLink(TASK, "task", "R-3", "3", by_id[TASK].fingerprint(), closed=True),
        GONE: IssueLink(GONE, "story", "R-4", "4", "x"),
        GONE_TASK: IssueLink(GONE_TASK, "task", "R-5", "5", "x"),
    }

    plan = plan_publish(issues, links)

    assert [(op.operation, op.item_id) for op in plan.operations] == [
        ("update", STORY),
        ("create", ORPHAN),
        ("update", TASK),
        ("close", GONE_TASK),
        ("close", GONE),
    ]
    assert plan.counts()["epic"].unchanged == 1


def test_the_description_holds_the_text_criteria_questions_link_and_marker() -> None:
    story, orphan = _issues()[1], _issues()[2]

    text = str(description(story)) + str(description(orphan))

    for expected in (
        "As a student.",
        "Acceptance criteria",
        "One slot.",
        "Open questions",
        "Who cancels?",
        "https://app.test/projects/p/backlog",
        f"ScopeSteps ID: {STORY}",
    ):
        assert expected in text
    assert "Assumptions" not in text


@pytest.mark.parametrize(
    ("typed", "site"),
    [
        ("team.atlassian.net", "https://team.atlassian.net"),
        ("https://Team.atlassian.net/jira/software/projects/WEB", "https://team.atlassian.net"),
        (" https://team.jira.com ", "https://team.jira.com"),
    ],
)
def test_jira_cloud_addresses_are_accepted(typed: str, site: str) -> None:
    assert normalise_site_url(typed) == site


@pytest.mark.parametrize(
    "typed",
    [
        "http://team.atlassian.net",
        "https://atlassian.net",
        "https://team.atlassian.net.evil.test",
        "https://localhost",
        "https://10.0.0.1",
        "https://user:pw@team.atlassian.net",
        "https://team.atlassian.net:8443",
    ],
)
def test_anything_but_a_jira_cloud_address_is_refused(typed: str) -> None:
    with pytest.raises(JiraSiteInvalidError):
        normalise_site_url(typed)


def test_project_keys_are_upper_cased_and_checked() -> None:
    assert normalise_project_key(" web ") == "WEB"
    with pytest.raises(InvalidInputError):
        normalise_project_key("1WEB")


def test_a_token_round_trips_and_a_tampered_one_is_refused() -> None:
    cipher = FernetTokenCipher(Fernet.generate_key().decode())

    stored = cipher.encrypt("synthetic-token")

    assert b"synthetic-token" not in stored
    assert cipher.decrypt(stored) == "synthetic-token"
    with pytest.raises(ValueError, match="cannot be read"):
        FernetTokenCipher(Fernet.generate_key().decode()).decrypt(stored)


def test_backoff_waits_as_jira_asks_or_doubles_up_to_fifteen_minutes() -> None:
    now = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)

    asked = backoff(3, 42, now) - now
    first = backoff(1, None, now) - now
    third = backoff(3, None, now) - now
    tenth = backoff(10, None, now) - now

    assert asked == timedelta(seconds=42)
    assert timedelta(seconds=30) <= first <= timedelta(seconds=36)
    assert timedelta(minutes=2) <= third <= timedelta(minutes=2, seconds=24)
    assert timedelta(minutes=15) <= tenth <= timedelta(minutes=18)


def _connection(expires_on: date | None = None, rejected: bool = False) -> JiraConnection:
    return JiraConnection(
        project_id=ProjectId(UUID(int=1)),
        site_url="https://team.atlassian.net",
        email="bot@example.test",
        token_ciphertext=b"x",
        jira_project=JiraProject("1", "WEB", "Web", IssueTypes("1", "2", "3")),
        auto_publish=False,
        revision=1,
        connected_by=UserId(UUID(int=2)),
        connected_at=datetime(2026, 1, 1, tzinfo=UTC),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
        token_expires_on=expires_on,
        token_rejected_at=datetime(2026, 1, 2, tzinfo=UTC) if rejected else None,
    )


@pytest.mark.parametrize(
    ("expires_on", "rejected", "state", "days"),
    [
        (None, False, "working", None),
        (date(2026, 12, 31), False, "working", 51),
        (date(2026, 11, 24), False, "expires_soon", 14),
        (date(2026, 11, 11), False, "expires_soon", 1),
        (date(2026, 11, 10), False, "expired", 0),
        (date(2026, 12, 31), True, "rejected", 51),
    ],
)
def test_a_tokens_state_follows_its_date_and_jiras_answer(
    expires_on: date | None, rejected: bool, state: str, days: int | None
) -> None:
    connection = _connection(expires_on, rejected)
    today = date(2026, 11, 10)

    assert (connection.token_state(today), connection.token_days_left(today)) == (state, days)


@pytest.mark.parametrize(("typed", "ok"), [(1, True), (400, True), (0, False), (401, False)])
def test_an_expiry_date_must_be_after_today_and_within_a_tokens_life(typed: int, ok: bool) -> None:
    today = date(2026, 11, 10)
    expires_on = today + timedelta(days=typed)

    if ok:
        assert check_token_expiry(expires_on, today) == expires_on
    else:
        with pytest.raises(InvalidInputError):
            check_token_expiry(expires_on, today)
