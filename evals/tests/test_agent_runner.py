"""Full agent runs on a pack with a scripted model: questions, scripted answers, scoring."""

import json
from typing import Any
from uuid import uuid4

from scopesteps.agent.client import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    Question,
    QuestionId,
    RunId,
    RunLimits,
    ToolCall,
    Usage,
)
from scopesteps.evals.agent_runner import ScriptedReviewer, passages, run_agent
from scopesteps.evals.packs import DATASETS_DIR, load_pack
from scopesteps.evals.runner import Pacer, summarize

CAMPUS = load_pack(DATASETS_DIR / "dev" / "campus-room-booking", "dev")
LIMITS = RunLimits(
    max_turns=6, max_tool_calls=8, max_output_tokens_per_call=8000, max_total_tokens=200_000
)


class Scripted:
    def __init__(self, results: list[ModelResult]) -> None:
        self.results = results
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        return self.results.pop(0)


def _result(text: str = "", calls: tuple[ToolCall, ...] = ()) -> ModelResult:
    return ModelResult(
        "test",
        "gemini-3.5-flash-lite",
        ModelTurn(({"type": "model_output", "text": text},)),
        text,
        calls,
        "tool_calls" if calls else "completed",
        Usage(input_tokens=100, output_tokens=10, total_tokens=110),
        40,
    )


def _ask(*block_sets: list[str]) -> ModelResult:
    questions: list[dict[str, Any]] = [
        {"subject": f"Q{i}", "question": "Which?", "why_it_matters": "Scope", "block_ids": blocks}
        for i, blocks in enumerate(block_sets, start=1)
    ]
    return _result(calls=(ToolCall("call-1", "request_clarification", {"questions": questions}),))


EMPTY = json.dumps({"statements": [], "items": [], "questions": [], "people": []})


def test_passages_are_numbered_like_the_single_pass_blocks() -> None:
    labels = [f"{p.source_kind} paragraph {p.ordinal}" for p in passages(CAMPUS)]

    assert labels[0] == "brief.md paragraph 1"
    assert len(labels) == len(CAMPUS.blocks["brief.md"]) + len(CAMPUS.blocks["transcript.md"])


def test_a_question_is_answered_from_the_annotation_whose_evidence_it_cites() -> None:
    reviewer = ScriptedReviewer(CAMPUS)
    conflict = sorted(reviewer.evidence["CF-01"])

    assert reviewer.match(_question(conflict)) is CAMPUS.annotations.get("CF-01")
    assert reviewer.match(_question(["B1"])) is None, "a heading matches no decision"


def test_an_agent_run_asks_gets_scripted_answers_drafts_and_is_scored() -> None:
    conflict = sorted(ScriptedReviewer(CAMPUS).evidence["CF-01"])
    provider = Scripted([_ask(conflict, ["B1"]), _result("READY"), _result(EMPTY), _result(EMPTY)])

    [record] = run_agent(
        provider,
        [CAMPUS],
        repeats=1,
        provider_name="gemini",
        model_id="gemini-3.5-flash-lite",
        limits=LIMITS,
        max_clarification_rounds=2,
        pacer=Pacer(requests_per_minute=10_000, max_calls=20, sleep=lambda _: None),
    )

    assert record.mode == "agent"
    assert record.valid, record.error
    assert record.calls == 4, "explore, explore after answers, draft, repair"
    assert record.metrics["agent_questions"] == 2
    assert record.metrics["agent_questions_unneeded"] == 1
    assert record.metrics["agent_decisions_asked"] == 1
    resumed = json.dumps([str(turn) for turn in provider.requests[1].history])
    assert "Three hours is the maximum" in resumed, "the scripted answer reaches the agent"
    verdicts = {r["annotation_id"]: r["verdict"] for r in record.results}
    assert verdicts["CF-01"] == "fail", "the answer was given but the empty draft did not use it"
    assert summarize([record])["agent"]["runs"] == 1
    assert [(q["matched"], q["reply"]) for q in record.questions] == [
        (["CF-01"], "answered"),
        ([], "skipped"),
    ]


def test_a_question_about_two_decisions_gets_both_parts_and_names_the_undecided_one() -> None:
    reviewer = ScriptedReviewer(CAMPUS)
    both = sorted(reviewer.evidence["MD-01"] | reviewer.evidence["MD-02"])

    reply = reviewer(_question(both))

    assert reply is not None
    assert reply.startswith("Users can cancel up to one hour before the start.")
    assert (
        "Not decided yet: There is no rule for what happens when someone does not turn up" in reply
    )


def _question(blocks: list[str]) -> Any:

    return Question(
        id=QuestionId(uuid4()),
        run_id=RunId(uuid4()),
        round=1,
        call_id="c",
        subject="s",
        text="t",
        why_it_matters="w",
        block_labels=tuple(blocks),
    )


def test_a_quota_error_stops_the_evaluation_and_keeps_earlier_runs() -> None:
    class Exhausted:
        def generate(self, request: ModelRequest) -> ModelResult:
            raise ModelProviderError("quota", "daily limit")

    records = run_agent(
        Exhausted(),
        [CAMPUS, CAMPUS],
        repeats=2,
        provider_name="gemini",
        model_id="gemini-3.5-flash-lite",
        limits=LIMITS,
        max_clarification_rounds=2,
        pacer=Pacer(
            requests_per_minute=10_000, max_calls=20, sleep=lambda _: None, log=lambda _: None
        ),
    )

    assert records == [], "no further runs are attempted after the quota is exhausted"
