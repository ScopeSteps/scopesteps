import json
from typing import Any, cast

import pytest
from pydantic import ValidationError

from scopesteps.agent.application.checks import (
    BASE_CHECKS,
    check_draft,
    requirement_blocks,
)
from scopesteps.agent.application.drafting import draft_single_pass
from scopesteps.agent.application.schemas import (
    DraftBacklog,
    DraftBacklogV1,
    DraftPatch,
    DraftQuestion,
    SourceBlockInput,
    apply_patch,
    parse_draft,
)
from scopesteps.agent.domain.model import ModelProviderError, ModelResult, ModelTurn, Usage
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider

BLOCKS = [
    SourceBlockInput("B1", "brief", "# Room booking"),
    SourceBlockInput("B2", "brief", "Users can book a room."),
    SourceBlockInput("B3", "transcript", "Recurring bookings are out of scope."),
    SourceBlockInput("A1", "reviewer answer", "Three hours is the maximum."),
]
BOOK = {"block_id": "B2", "quote": "book a room"}
RECURRING = {"block_id": "B3", "quote": "Recurring bookings are out of scope."}
ANSWER = {"block_id": "A1", "quote": "Three hours is the maximum."}


def _draft(
    *,
    statements: list[dict[str, Any]] | None = None,
    covers: list[str] | None = None,
    extra: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    story_criteria: list[dict[str, Any]] = [
        {"text": "Booking works", "origin": "source", "citations": [BOOK]}
    ]
    return {
        "statements": statements
        if statements is not None
        else [
            {"id": "T1", "kind": "confirmed", "summary": "Book a room", "citations": [BOOK]},
            {"id": "T2", "kind": "exclusion", "summary": "No recurring", "citations": [RECURRING]},
        ],
        "items": [
            {
                "ref": "E1",
                "kind": "epic",
                "parent_ref": None,
                "title": "Booking",
                "description": "Booking.",
                "criteria": [],
                "assumptions": [],
                "open_questions": [],
                "covers": [],
            },
            {
                "ref": "S1",
                "kind": "story",
                "parent_ref": "E1",
                "title": "Book",
                "description": "As a student, I want to book a room, so that I can study.",
                "criteria": story_criteria + (extra or []),
                "assumptions": [],
                "open_questions": [],
                "covers": covers if covers is not None else ["T1"],
            },
        ],
        "questions": [],
    }


ACCOUNT = requirement_blocks(BLOCKS, exclude={"A1"})


def test_requirement_blocks_skip_headings_and_excluded_blocks() -> None:
    assert ACCOUNT == ["B2", "B3"]


def test_a_traceable_draft_passes() -> None:
    draft = DraftBacklog.model_validate(_draft())

    assert check_draft(draft, BLOCKS, account_blocks=ACCOUNT) == []


@pytest.mark.parametrize(
    ("data", "kwargs", "problem"),
    [
        (
            _draft(
                statements=[
                    {"id": "T1", "kind": "confirmed", "summary": "Book", "citations": [BOOK]}
                ]
            ),
            {"account_blocks": ACCOUNT},
            "source B3 is not cited by any statement",
        ),
        (_draft(covers=[]), {}, "confirmed statement T1 'Book a room' is not covered by any story"),
        (_draft(covers=["T1", "T2"]), {}, "S1 covers exclusion statement T2"),
        (_draft(), {"answer_blocks": {"A1"}}, "reviewer answer A1 is not cited"),
    ],
)
def test_traceability_problems(data: dict[str, Any], kwargs: dict[str, Any], problem: str) -> None:
    draft = DraftBacklog.model_validate(data)

    assert any(found.startswith(problem) for found in check_draft(draft, BLOCKS, **kwargs))


def test_a_sourced_criterion_citing_the_answer_satisfies_the_answer_check() -> None:
    draft = DraftBacklog.model_validate(
        _draft(extra=[{"text": "Max 3 hours", "origin": "source", "citations": [ANSWER]}])
    )

    assert check_draft(draft, BLOCKS, answer_blocks={"A1"}) == []


def test_base_check_set_ignores_traceability() -> None:
    draft = DraftBacklog.model_validate(_draft(covers=[]))

    assert check_draft(draft, BLOCKS, account_blocks=["B3"], enabled=BASE_CHECKS) == []


def test_schema_rejects_duplicate_statement_ids() -> None:
    data = _draft()
    data["statements"].append(dict(data["statements"][0]))

    with pytest.raises(ValidationError, match="Statement ids must be unique"):
        DraftBacklog.model_validate(data)


def test_schema_rejects_covers_of_unknown_statements() -> None:
    data = _draft(covers=["T9"])

    with pytest.raises(ValidationError, match="S1 covers unknown statements T9"):
        DraftBacklog.model_validate(data)


def test_parse_draft_reads_both_schema_versions() -> None:
    v1 = {
        "statements": [{"kind": "confirmed", "summary": "x", "citations": [BOOK]}],
        "items": [],
        "questions": [],
    }

    assert isinstance(parse_draft(_draft()), DraftBacklog)
    assert isinstance(parse_draft(v1), DraftBacklogV1)


def _result(text: str) -> ModelResult:
    return ModelResult(
        "t", "m", ModelTurn(({"type": "model_output"},)), text, (), "completed", Usage(), 1
    )


def _story(covers: list[str]) -> dict[str, Any]:
    return next(item for item in _draft(covers=covers)["items"] if item["ref"] == "S1")


def _patch(
    statements: list[dict[str, Any]] | None = None,
    items: list[dict[str, Any]] | None = None,
    questions: list[dict[str, Any]] | None = None,
) -> str:
    return json.dumps(
        {"statements": statements or [], "items": items or [], "questions": questions or []}
    )


def test_v3_repairs_with_a_patch_of_only_the_changed_parts() -> None:
    untraceable = json.dumps(_draft(covers=[]))
    provider = ScriptedProvider([_result(untraceable), _result(_patch(items=[_story(["T1"])]))])

    outcome = draft_single_pass(provider, BLOCKS[:3], max_output_tokens=100, prompt="draft-v3")

    schema = cast(dict[str, Any], provider.requests[0].output_schema)
    assert "covers" in schema["properties"]["items"]["items"]["properties"]
    assert (outcome.repair, outcome.repaired, outcome.check_problems) == ("targeted", True, ())
    assert outcome.repair_triggers == ("uncovered_confirmed_statement",)
    assert outcome.draft is not None
    assert [item.ref for item in outcome.draft.items] == ["E1", "S1"]
    repair = provider.requests[1]
    assert repair.history[1] == _result(untraceable).turn, "the model sees its own draft"
    assert "- confirmed statement T1 'Book a room' is not covered" in str(repair.history[2])
    patch_schema = cast(dict[str, Any], repair.output_schema)
    assert set(patch_schema["properties"]) == {"statements", "items", "questions"}


def test_patch_replaces_by_id_and_number_and_adds_the_rest() -> None:
    draft = DraftBacklog.model_validate(_draft())
    question = {"subject": "Hours", "question": "How long?", "why_it_matters": "Limits"}
    draft = draft.model_copy(
        update={"questions": [DraftQuestion.model_validate(question | {"citations": [BOOK]})]}
    )
    patch = DraftPatch.model_validate_json(
        _patch(
            statements=[
                {"id": "T1", "kind": "confirmed", "summary": "Book", "citations": [BOOK]},
                {"id": "T3", "kind": "context", "summary": "Intro", "citations": [RECURRING]},
            ],
            questions=[
                question | {"citations": [RECURRING], "replaces": 1},
                question | {"citations": [BOOK], "replaces": None},
            ],
        )
    )

    patched = apply_patch(draft, patch)

    assert [(s.id, s.summary) for s in patched.statements] == [
        ("T1", "Book"),
        ("T2", "No recurring"),
        ("T3", "Intro"),
    ]
    assert [q.citations[0].block_id for q in patched.questions] == ["B3", "B2"]


def test_a_patch_that_breaks_the_draft_keeps_the_draft_and_its_problems() -> None:
    untraceable = json.dumps(_draft(covers=[]))
    provider = ScriptedProvider([_result(untraceable), _result(_patch(items=[_story(["T9"])]))])

    outcome = draft_single_pass(provider, BLOCKS[:3], max_output_tokens=100, prompt="draft-v3")

    assert outcome.draft is not None
    assert (outcome.repair, outcome.repaired) == ("targeted", False)
    assert outcome.check_problems


def test_a_failed_repair_call_keeps_the_draft_and_counts_the_call() -> None:
    untraceable = json.dumps(_draft(covers=[]))
    timeout = ModelProviderError("timeout", "The model provider did not respond in time")
    provider = ScriptedProvider([_result(untraceable), timeout])

    outcome = draft_single_pass(provider, BLOCKS[:3], max_output_tokens=100, prompt="draft-v3")

    assert outcome.draft is not None
    assert outcome.calls == 2
    assert outcome.repair_error == "timeout: The model provider did not respond in time"
    assert outcome.check_problems


def test_a_failed_first_call_still_raises() -> None:
    provider = ScriptedProvider([ModelProviderError("unavailable", "down")])

    with pytest.raises(ModelProviderError):
        draft_single_pass(provider, BLOCKS[:3], max_output_tokens=100, prompt="draft-v3")


def test_v2_quote_problems_name_the_statement_id() -> None:
    wrong = {"block_id": "B2", "quote": "book a desk"}
    draft = DraftBacklog.model_validate(
        _draft(
            statements=[{"id": "T1", "kind": "confirmed", "summary": "Book", "citations": [wrong]}]
        )
    )

    assert "statement T1 quote is not verbatim from B2" in check_draft(draft, BLOCKS)


def test_v2_keeps_its_original_schema_and_checks() -> None:
    v1_draft: dict[str, list[Any]] = {"statements": [], "items": [], "questions": []}
    provider = ScriptedProvider([_result(json.dumps(v1_draft))])

    outcome = draft_single_pass(provider, BLOCKS[:3], max_output_tokens=100, prompt="draft-v2")

    schema = cast(dict[str, Any], provider.requests[0].output_schema)
    assert "covers" not in schema["properties"]["items"]["items"]["properties"]
    assert (outcome.calls, outcome.check_problems) == (1, ())


def _block_id_enums(schema: object) -> list[list[str]]:
    found: list[list[str]] = []
    if isinstance(schema, dict):
        node = cast(dict[str, Any], schema)
        properties = node.get("properties")
        if isinstance(properties, dict) and "block_id" in properties:
            found.append(cast(dict[str, Any], properties)["block_id"].get("enum"))
        for value in node.values():
            found += _block_id_enums(value)
    elif isinstance(schema, list):
        for value in cast(list[Any], schema):
            found += _block_id_enums(value)
    return found


def test_v3_requests_only_allow_citing_the_requests_blocks() -> None:
    untraceable = json.dumps(_draft(covers=[]))
    provider = ScriptedProvider([_result(untraceable), _result(_patch(items=[_story(["T1"])]))])

    draft_single_pass(provider, BLOCKS[:3], max_output_tokens=100, prompt="draft-v3")

    for request in provider.requests:
        enums = _block_id_enums(request.output_schema)
        assert enums
        assert all(enum == ["B1", "B2", "B3"] for enum in enums), "drafts and patches alike"


def test_v2_requests_stay_as_they_were_measured() -> None:
    empty: dict[str, list[object]] = {"statements": [], "items": [], "questions": []}
    provider = ScriptedProvider([_result(json.dumps(empty))])

    draft_single_pass(provider, BLOCKS[:3], max_output_tokens=100, prompt="draft-v2")

    assert all(enum is None for enum in _block_id_enums(provider.requests[0].output_schema))


def test_a_full_repair_after_unparseable_output_records_why() -> None:
    provider = ScriptedProvider([_result(""), _result(json.dumps(_draft()))])

    outcome = draft_single_pass(provider, BLOCKS[:3], max_output_tokens=100, prompt="draft-v3")

    assert (outcome.repair, outcome.repair_triggers) == ("full", ("empty_output",))


def test_unparseable_v3_output_is_regenerated_concisely_not_replayed() -> None:
    provider = ScriptedProvider([_result(""), _result(json.dumps(_draft()))])

    outcome = draft_single_pass(provider, BLOCKS[:3], max_output_tokens=100, prompt="draft-v3")

    assert outcome.draft is not None
    retry = provider.requests[1].history
    assert len(retry) == 1, "the empty answer is not sent back"
    assert "cut off at the length limit" in str(retry[0])


def test_v3_requests_constrain_statement_ids_and_covers() -> None:
    provider = ScriptedProvider([_result(json.dumps(_draft()))])

    draft_single_pass(provider, BLOCKS[:3], max_output_tokens=100, prompt="draft-v3")

    schema = cast(dict[str, Any], provider.requests[0].output_schema)
    statement = schema["properties"]["statements"]["items"]["properties"]["id"]
    covers = schema["properties"]["items"]["items"]["properties"]["covers"]["items"]
    assert statement["enum"][:2] == ["T1", "T2"]
    assert len(statement["enum"]) == 60
    assert covers["enum"] == statement["enum"]
