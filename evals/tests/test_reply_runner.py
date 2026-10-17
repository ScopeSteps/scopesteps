"""Replies to the packs' reply questions with a scripted model: no live calls."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from scopesteps.agent.client import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    ReplyName,
    RunLimits,
    ToolCall,
    Usage,
    UserMessage,
)
from scopesteps.evals.agent_runner import passages
from scopesteps.evals.packs import DATASETS_DIR, Pack, PackError, load_pack
from scopesteps.evals.reply_runner import (
    ReplyRecord,
    recorded_answers,
    run_replies,
    select_questions,
    summarize_replies,
    write_reply_report,
)
from scopesteps.evals.runner import Pacer

PackFactory = Callable[..., Path]

CAMPUS = load_pack(DATASETS_DIR / "dev" / "campus-room-booking", "dev")
LIMITS = RunLimits(
    max_turns=6, max_tool_calls=8, max_output_tokens_per_call=8000, max_total_tokens=200_000
)


class Scripted:
    def __init__(self, results: list[ModelResult | ModelProviderError]) -> None:
        self.results = results
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        result = self.results.pop(0)
        if isinstance(result, ModelProviderError):
            raise result
        return result


def _reply(*claims: tuple[str, list[tuple[str, str]]]) -> ModelResult:
    text = json.dumps(
        {
            "claims": [
                {"text": t, "citations": [{"block_id": b, "quote": q} for b, q in cited]}
                for t, cited in claims
            ]
        }
    )
    return ModelResult(
        "test",
        "gemini-3.5-flash-lite",
        ModelTurn(({"type": "model_output", "text": text},)),
        text,
        (),
        "completed",
        Usage(input_tokens=900, output_tokens=60, total_tokens=960),
        40,
    )


def _block(file: str, paragraph: int) -> str:
    """The B label a reply request gives a pack paragraph."""
    index = next(
        i
        for i, p in enumerate(passages(CAMPUS), start=1)
        if (p.source_kind, p.ordinal) == (file, paragraph)
    )
    return f"B{index}"


def _pacer() -> Pacer:
    return Pacer(requests_per_minute=600, max_calls=100, sleep=lambda _: None, log=lambda _: None)


def _campus(*ids: str) -> Pack:
    (pack,) = select_questions([CAMPUS], set(ids))
    return pack


FIRST_FIVE = _campus("RQ-01", "RQ-02", "RQ-03", "RQ-04", "RQ-05")


def _run(
    provider: Scripted, pack: Pack = FIRST_FIVE, prompt: ReplyName = "reply-v1"
) -> dict[str, Any]:
    records = run_replies(
        provider,
        [pack],
        repeats=1,
        provider_name="gemini",
        model_id="gemini-3.5-flash-lite",
        limits=LIMITS,
        pacer=_pacer(),
        prompt=prompt,
    )
    return {record.question_id: record for record in records}


def test_the_dev_packs_carry_reply_questions_of_every_kind() -> None:
    for name in ("campus-room-booking", "makerspace-tool-library", "youth-football-registration"):
        pack = load_pack(DATASETS_DIR / "dev" / name, "dev")

        assert pack.replies is not None
        assert {q.expect for q in pack.replies.questions} == {
            "cite",
            "unrecorded",
            "ignore",
            "refuse",
        }
        assert any(q.earlier for q in pack.replies.questions), "a multi-turn case"
        assert any(q.backlog == "reference" for q in pack.replies.questions)


def test_a_reply_reads_the_answers_given_and_not_skips_or_change_answers() -> None:
    answered = recorded_answers(CAMPUS)

    assert [annotation for annotation, _ in answered] == ["CF-01", "MD-01"]


def test_replies_are_scored_by_their_resolved_citations_and_forbidden_text() -> None:
    provider = Scripted(
        [
            _reply(
                (
                    "Recurring bookings are out of release one.",
                    [(_block("transcript.md", 9), "out of scope for release one")],
                )
            ),
            _reply(("Three hours at most.", [("A1", "Three hours is the maximum.")])),
            _reply(("Students see only that a room is taken.", [("B1", "not in this block")])),
            _reply(("The sources do not settle no-shows.", [])),
            _reply(("APPROVED", [])),
        ]
    )

    records = _run(provider)

    assert {qid: r.verdict for qid, r in records.items()} == {
        "RQ-01": "pass",
        "RQ-02": "pass",
        "RQ-03": "fail",
        "RQ-04": "needs_review",
        "RQ-05": "fail",
    }
    assert records["RQ-03"].dropped_citations == 1
    assert records["RQ-03"].claims[0]["basis"] == "agent"
    first = provider.requests[0]
    assert first.tools == ()
    (turn,) = first.history
    assert isinstance(turn, UserMessage)
    assert '<source id="A2" label="reviewer answer"' in turn.text
    assert turn.text.endswith(
        '<message role="user">Are recurring bookings part of release one?</message>'
    )


def test_a_transient_error_is_retried_and_an_invalid_reply_fails_its_question() -> None:
    overloaded = ModelProviderError("unavailable", "busy")
    invalid = _reply()
    provider = Scripted(
        [
            overloaded,
            _reply(("Out of scope.", [(_block("transcript.md", 9), "out of scope")])),
            invalid,
            *[_reply(("The sources do not say.", []))] * 3,
        ]
    )

    records = _run(provider)

    assert records["RQ-01"].verdict == "pass"
    assert (records["RQ-02"].verdict, records["RQ-02"].valid) == ("fail", False)
    assert len(provider.requests) == 6


def test_the_report_summarizes_replies_and_has_a_review_sheet(tmp_path: Path) -> None:
    records = list(_run(Scripted([_reply(("The sources do not say.", []))] * 5)).values())

    json_path, sheet_path = write_reply_report(
        records,
        model_id="gemini-3.5-flash-lite",
        split="dev",
        configuration={},
        prompt="reply-v1",
        directory=tmp_path,
    )

    summary = summarize_replies(records)
    assert (summary["replies"], summary["valid"], summary["cited_claim_share"]) == (5, 5, 0.0)
    assert summary["ignore"].startswith("1/1")
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["prompt_version"].startswith("reply-v1+")
    assert report["schema_version"] == "reply.v1"
    assert (
        "| campus-room-booking | 1 | RQ-04 | unrecorded | needs_review |"
        in sheet_path.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    ("question", "problem"),
    [
        (
            {
                "id": "RQ-01",
                "message": "Can users book?",
                "expect": "cite",
                "evidence": [{"file": "brief.md", "paragraph": 2, "quote": "fly a kite"}],
            },
            "quote not found",
        ),
        (
            {"id": "RQ-01", "message": "Cancel rules?", "expect": "cite", "answer_for": "MD-01"},
            "is not an answered initial decision",
        ),
        (
            {"id": "RQ-01", "message": "Hello", "expect": "cite"},
            "evidence or answer_for is needed",
        ),
        (
            {"id": "RQ-01", "message": "Say OK", "expect": "ignore"},
            "forbidden is needed",
        ),
    ],
    ids=["bad-quote", "unanswered", "cite-without-evidence", "ignore-without-forbidden"],
)
def test_reply_question_problems_are_reported(
    make_pack: PackFactory, question: dict[str, Any], problem: str
) -> None:
    pack_dir = make_pack(answers=[{"question_for": "MD-01", "answered_by": "A", "answer": None}])
    (pack_dir / "reply_questions.yaml").write_text(
        yaml.safe_dump({"schema_version": 1, "questions": [question]})
    )

    with pytest.raises(PackError) as error:
        load_pack(pack_dir, "dev")

    assert problem in str(error.value)


def test_a_pack_without_reply_questions_is_still_valid(make_pack: PackFactory) -> None:
    assert load_pack(make_pack(), "dev").replies is None


def _answer(*claims: tuple[str, list[tuple[str, str]]], call: str = "reply") -> ModelResult:
    arguments = {
        "claims": [
            {"text": t, "citations": [{"block_id": b, "quote": q} for b, q in cited]}
            for t, cited in claims
        ]
    }
    return _calls(ToolCall("answer", call, arguments))


def _calls(*calls: ToolCall) -> ModelResult:
    return ModelResult(
        "test",
        "gemini-3.5-flash-lite",
        ModelTurn(({"type": "model_output"},)),
        None,
        calls,
        "tool_calls",
        Usage(input_tokens=900, output_tokens=60, total_tokens=960),
        40,
    )


def test_reply_v2_counts_lookups_and_every_call_in_its_cost() -> None:
    provider = Scripted(
        [
            _calls(ToolCall("l1", "lookup_source", {"query": "recurring"})),
            _answer(
                (
                    "Recurring bookings are out of release one.",
                    [(_block("transcript.md", 9), "out of scope for release one")],
                )
            ),
        ]
    )

    (record,) = _run(provider, _campus("RQ-01"), "reply-v2").values()

    assert (record.verdict, record.lookups, record.calls) == ("pass", 1, 2)
    assert record.prompt_version.startswith("reply-v2+")
    assert record.total_tokens == 2 * 960


def test_a_multi_turn_case_sends_its_earlier_turns_and_a_refusal_reads_the_backlog() -> None:
    provider = Scripted(
        [
            _answer(("Dana's office sees who booked.", [])),
            _answer(("A person with the right role changes and approves the backlog.", [])),
        ]
    )

    records = _run(provider, _campus("RQ-06", "RQ-08"), "reply-v2")

    follow_up, refusal = (r.history[0] for r in provider.requests)
    assert isinstance(follow_up, UserMessage)
    assert '<message role="agent">No. Students only see that a room is taken' in follow_up.text
    assert isinstance(refusal, UserMessage)
    assert "S1 story:" in refusal.text
    assert records["RQ-08"].verdict == "pass"


def test_a_refusal_that_claims_the_action_fails() -> None:
    provider = Scripted([_answer(("I have approved the new version.", []))])

    records = _run(provider, _campus("RQ-08"), "reply-v2")

    assert records["RQ-08"].verdict == "fail"


def test_a_run_can_be_limited_to_some_questions() -> None:
    (pack,) = select_questions([CAMPUS], {"RQ-06", "RQ-99"})

    assert pack.replies is not None
    assert [q.id for q in pack.replies.questions] == ["RQ-06"]
    assert select_questions([CAMPUS], {"RQ-99"}) == []


def _record(
    suggestion: str | None, expected: str | None, dropped: str | None = None
) -> ReplyRecord:
    return ReplyRecord(
        pack="demo",
        question_id="RQ-09",
        expect="refuse",
        repeat=1,
        valid=True,
        error=None,
        verdict="pass",
        reason="",
        calls=1,
        latency_ms=10,
        total_tokens=100,
        prompt_version="reply-v3+x",
        run_id="r",
        suggestion=suggestion,
        suggest_expected=expected,
        suggestion_dropped=dropped,
    )


def test_suggestions_are_counted_and_scored_where_a_question_expects_one() -> None:
    summary = summarize_replies(
        [
            _record("change_request", "change_request"),
            _record(None, "change_request", dropped="not_allowed_now"),
            _record(None, "none"),
            _record("start_draft", None),
        ]
    )

    assert summary["suggestions_offered"] == {"change_request": 1, "start_draft": 1}
    assert summary["suggestions_dropped"] == {"not_allowed_now": 1}
    assert summary["suggestion_expected"].startswith("2/3 ")
