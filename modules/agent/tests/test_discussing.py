"""Talking a proposed change through (reply-v5): the prompt, the label check and the only
suggestion a discussion may offer. Synthetic data; no model calls."""

import pytest

from scopesteps.agent.application.reply_tools import NO_BACKLOG
from scopesteps.agent.application.replying import (
    CONVERSATION_REPLY,
    DISCUSS_REPLIES,
    DISCUSS_REPLY,
    MAX_DISCUSS_CLAIMS,
    REPLY_PROMPTS,
    REPLY_SCHEMAS,
    ReplyClaim,
    ReplyOutputV3,
    ReplySuggestion,
    cut_unknown_labels,
    reply_prompt_version,
)
from scopesteps.agent.application.suggestions import SuggestionState, check_suggestion


def test_reply_v5_is_reply_v4_plus_the_discussion_rules() -> None:
    extra = REPLY_PROMPTS["reply-v5"].removeprefix(REPLY_PROMPTS["reply-v4"])

    assert REPLY_PROMPTS["reply-v5"].startswith(REPLY_PROMPTS["reply-v4"])
    assert extra.lstrip().startswith("Talking a change through:")
    for rule in (
        "never reverse an exclusion or decision",
        "an approver",
        f"At most {MAX_DISCUSS_CLAIMS} claims",
        "Suggest only change_request",
        "Code removes a claim naming any other",
    ):
        assert rule in extra
    assert REPLY_SCHEMAS["reply-v5"] == REPLY_SCHEMAS["reply-v4"]


def test_reply_v4_is_unchanged_and_still_answers_plain_messages() -> None:
    assert reply_prompt_version("reply-v4") == "reply-v4+c76027aeaec0"
    assert (CONVERSATION_REPLY, DISCUSS_REPLY) == ("reply-v4", "reply-v5")
    assert sorted(DISCUSS_REPLIES) == ["reply-v5"]


def _output(*texts: str) -> ReplyOutputV3:
    return ReplyOutputV3(claims=[ReplyClaim(text=text, citations=[]) for text in texts])


def test_a_claim_naming_a_label_not_shown_is_cut_and_counted() -> None:
    known = {"B1", "B2", "A1", "E1", "S1", "S1.C1", "X1", "D1"}
    output = _output(
        "It extends S1 and touches S1.C1.",
        "It conflicts with X2.",
        "B2 says so, and D1 settled it.",
        "It would change S4.C1.",
        "No label here.",
    )

    kept, cut = cut_unknown_labels(output, known)

    assert [claim.text for claim in kept.claims] == [
        "It extends S1 and touches S1.C1.",
        "B2 says so, and D1 settled it.",
        "No label here.",
    ]
    assert cut == 2
    assert isinstance(kept, ReplyOutputV3)


def _state(*, has_baseline: bool = True) -> SuggestionState:
    return SuggestionState(
        has_baseline=has_baseline,
        backlog=None,
        labels=NO_BACKLOG,
        has_sources=True,
        message="Let's go ahead.",
        kinds=frozenset({"change_request"}),
    )


def test_a_discussion_keeps_a_change_request_under_the_usual_rules() -> None:
    raw = ReplySuggestion(kind="change_request", request_text="Allow weekly bookings.")

    kept = check_suggestion(raw, _state())
    without_baseline = check_suggestion(raw, _state(has_baseline=False))
    blank = check_suggestion(ReplySuggestion(kind="change_request", request_text=" "), _state())

    assert kept.kept is not None
    assert kept.kept.request_text == "Allow weekly bookings."
    assert (without_baseline.kept, without_baseline.dropped) == (None, "not_allowed_now")
    assert (blank.kept, blank.dropped) == (None, "invalid_text")


@pytest.mark.parametrize(
    "raw",
    [
        ReplySuggestion(kind="start_draft"),
        ReplySuggestion(kind="answer_decision", decision="D1", answer="Let's go ahead."),
    ],
)
def test_a_discussion_offers_no_other_kind_of_suggestion(raw: ReplySuggestion) -> None:
    check = check_suggestion(raw, _state())

    assert (check.kept, check.dropped) == (None, "not_offered_here")


def test_a_free_reply_still_offers_every_kind() -> None:
    state = SuggestionState(
        has_baseline=False,
        backlog=None,
        labels=NO_BACKLOG,
        has_sources=True,
        message="Draft it, please.",
    )

    assert check_suggestion(ReplySuggestion(kind="start_draft"), state).kept is not None
