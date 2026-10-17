"""Whether a reply's suggested next step may be offered (ADR 0013).

The model proposes; code decides. A suggestion is kept only when the project could take that
step now, and only with values that hold: a change request's text is a valid message, and an
answer to a decision is copied from the reviewer's own message, so neither the model nor text in
a source can put words in the reviewer's mouth. Anything else is dropped, never repaired; the
step records why, in a code. Accepting a kept suggestion still goes through the existing endpoint,
which repeats every check.
"""

from dataclasses import dataclass
from typing import Literal

from scopesteps.agent.application.reply_tools import BacklogLabels
from scopesteps.agent.application.replying import ReplySuggestion
from scopesteps.agent.domain.conversation import InvalidMessageError, clean_message_text
from scopesteps.agent.domain.suggestion import ProposedSuggestion
from scopesteps.backlog.client import BacklogOutline, VersionState
from scopesteps.sources.client import quote_matches

DropReason = Literal[
    "not_allowed_now",
    "invalid_text",
    "unknown_decision",
    "scope_decision",
    "answer_not_in_message",
]


@dataclass(frozen=True)
class SuggestionState:
    """What the project allows as the reply finishes."""

    has_baseline: bool
    backlog: BacklogOutline | None
    labels: BacklogLabels
    has_sources: bool
    message: str
    """The reviewer's message the reply answers."""


@dataclass(frozen=True)
class SuggestionCheck:
    kept: ProposedSuggestion | None
    dropped: DropReason | None = None


def check_suggestion(raw: ReplySuggestion, state: SuggestionState) -> SuggestionCheck:
    match raw.kind:
        case "change_request":
            return _change_request(raw, state)
        case "answer_decision":
            return _answer_decision(raw, state)
        case "start_draft":
            if not state.has_sources:
                return SuggestionCheck(None, "not_allowed_now")
            return SuggestionCheck(ProposedSuggestion("start_draft"))


def _change_request(raw: ReplySuggestion, state: SuggestionState) -> SuggestionCheck:
    # As submit_change_request requires: a baseline to change, and no candidate in review.
    in_review = state.backlog is not None and state.backlog.state == VersionState.IN_REVIEW
    if not state.has_baseline or in_review:
        return SuggestionCheck(None, "not_allowed_now")
    try:
        text = clean_message_text(raw.request_text)
    except InvalidMessageError:
        return SuggestionCheck(None, "invalid_text")
    return SuggestionCheck(ProposedSuggestion("change_request", request_text=text))


def _answer_decision(raw: ReplySuggestion, state: SuggestionState) -> SuggestionCheck:
    backlog = state.backlog
    if backlog is None or backlog.state not in {VersionState.DRAFT, VersionState.IN_REVIEW}:
        return SuggestionCheck(None, "not_allowed_now")
    decision = state.labels.decisions.get(raw.decision)
    if decision is None:
        return SuggestionCheck(None, "unknown_decision")
    if decision.kind == "scope_reversal":
        # Settled by reverse or keep, never by a written answer.
        return SuggestionCheck(None, "scope_decision")
    try:
        answer = clean_message_text(raw.answer)
    except InvalidMessageError:
        return SuggestionCheck(None, "invalid_text")
    if not quote_matches(answer, state.message):
        return SuggestionCheck(None, "answer_not_in_message")
    return SuggestionCheck(
        ProposedSuggestion(
            "answer_decision",
            version_id=backlog.version_id,
            decision_id=decision.id,
            decision_subject=decision.subject,
            answer=answer,
        )
    )
