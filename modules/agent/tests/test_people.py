"""People in a draft: the schema, the checks, the repair, and what code keeps of them.

All names are synthetic.
"""

import json
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from scopesteps.agent.application.candidate import to_people
from scopesteps.agent.application.checks import PEOPLE_CHECKS, TRACEABILITY_CHECKS, check_draft
from scopesteps.agent.application.drafting import (
    DRAFT_PROMPTS,
    PROMPT_CHECKS,
    PROMPT_SCHEMAS,
    draft_single_pass,
    prompt_version,
    sources_message,
)
from scopesteps.agent.application.ports import Passage
from scopesteps.agent.application.schemas import (
    DraftBacklogV3,
    DraftBacklogV4,
    DraftPatchV4,
    SourceBlockInput,
    apply_patch,
    constrain_ids,
    parse_draft,
    provider_schema,
)
from scopesteps.agent.application.steps import AGENT_SCHEMA_VERSION, DRAFT_PROMPT
from scopesteps.agent.domain.model import ModelRequest, ModelResult, ModelTurn, Usage, UserMessage
from scopesteps.agent.infrastructure.providers import groq
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.agent.infrastructure.providers.openai_compatible import (
    build_request_body,
    strict_schema,
)
from scopesteps.projects.client import (
    MAX_PEOPLE_PER_RUN,
    MAX_QUOTE_CHARS,
    MAX_SAID_CHARS,
    extraction_problems,
)
from scopesteps.sources.client import SourceBlockId, SourceVersionId

ATTENDEES = "Attendees: Dana Ruiz (Facilities Manager), Sam Okafor (Student Union representative)."
TEXTS = {
    "B1": "Users can book a room.",
    "B2": ATTENDEES,
    "B3": "**Dana (Facilities):** Three hours is the most I want for a single booking.",
    "B4": "**Alex (Product owner):** Cancellation stays open until Dana confirms.",
}
BLOCKS = [SourceBlockInput(label, "transcript", text) for label, text in TEXTS.items()]
ANSWER = SourceBlockInput("A1", "reviewer answer", "Dana Ruiz decides the cancellation rule.")
VERSION = SourceVersionId(UUID(int=1))
PASSAGES = {
    label: Passage(SourceBlockId(UUID(int=10 + index)), VERSION, "transcript", index, text)
    for index, (label, text) in enumerate(TEXTS.items(), start=1)
}

BOOK = {"block_id": "B1", "quote": "book a room"}
NAMED = {"block_id": "B2", "quote": "Dana Ruiz (Facilities Manager)"}
SAID = {"block_id": "B3", "quote": "Three hours is the most I want"}
CONFIRMS = {"block_id": "B4", "quote": "stays open until Dana confirms"}
CONTEXT = [NAMED, {"block_id": "B3", "quote": "Three hours"}, {"block_id": "B4", "quote": "open"}]


def _person(ref: str = "P1", **changes: Any) -> dict[str, Any]:
    person: dict[str, Any] = {
        "ref": ref,
        "name": "Dana Ruiz",
        "role": "Facilities Manager",
        "said": "Wants a shorter maximum booking.",
        "citations": [NAMED, SAID],
        "rights": "not_stated",
        "rights_citations": [],
    }
    return person | changes


def _draft(*people: dict[str, Any]) -> dict[str, Any]:
    return {
        "statements": [
            {"id": "T1", "kind": "confirmed", "summary": "Book a room", "citations": [BOOK]},
            {"id": "T2", "kind": "context", "summary": "Meeting", "citations": CONTEXT},
        ],
        "items": [
            {
                "ref": "E1",
                "kind": "epic",
                "parent_ref": None,
                "title": "Booking",
                "description": "Booking rooms.",
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
                "criteria": [
                    {"text": "A room is booked.", "origin": "source", "citations": [BOOK]}
                ],
                "assumptions": [],
                "open_questions": [],
                "covers": ["T1"],
            },
        ],
        "questions": [],
        "people": list(people),
    }


def _checked(*people: dict[str, Any]) -> list[str]:
    return check_draft(
        DraftBacklogV4.model_validate(_draft(*people)), BLOCKS, enabled=PEOPLE_CHECKS
    )


def _result(text: str) -> ModelResult:
    return ModelResult(
        "t", "m", ModelTurn(({"type": "model_output"},)), text, (), "completed", Usage(), 1
    )


def _patch(*people: dict[str, Any]) -> str:
    return json.dumps({"statements": [], "items": [], "questions": [], "people": list(people)})


def test_a_draft_with_cited_people_passes() -> None:
    stated = _person(rights="decides", rights_citations=[CONFIRMS])

    assert (
        _checked(
            stated, _person("P2", name="Sam Okafor", citations=[NAMED | {"quote": "Sam Okafor"}])
        )
        == []
    )


@pytest.mark.parametrize(
    ("person", "problem"),
    [
        (_person(citations=[]), "person P1 'Dana Ruiz' has no citation"),
        (
            _person(name="Morgan Vale"),
            "person P1 'Morgan Vale' is not named in any block they cite",
        ),
        (_person(citations=[SAID]), "person P1 'Dana Ruiz' is not named in any block they cite"),
        (_person(rights="decides"), "person P1 has rights 'decides' with no citation"),
        (_person(rights="advises"), "person P1 has rights 'advises' with no citation"),
        (
            _person(citations=[NAMED, {"block_id": "B9", "quote": "x"}]),
            "person P1 cites unknown block B9",
        ),
        (
            _person(
                rights="decides", rights_citations=[{"block_id": "B4", "quote": "Dana decides"}]
            ),
            "person P1 rights quote is not verbatim from B4",
        ),
    ],
)
def test_people_checks(person: dict[str, Any], problem: str) -> None:
    assert [found for found in _checked(person) if found.startswith(problem)] != []


def test_a_first_name_the_cited_block_uses_is_enough() -> None:
    assert _checked(_person(name="Dana", role="", citations=[SAID])) == []


def test_earlier_prompts_keep_their_schema_checks_and_text() -> None:
    assert PROMPT_CHECKS["draft-v4"] == TRACEABILITY_CHECKS
    assert PROMPT_SCHEMAS["draft-v4"] == "draft-backlog.v3"
    assert prompt_version("draft-v3") == "draft-v3+6e5ee74a76e8"
    assert prompt_version("draft-v4") == "draft-v4+6fb14e9e8eb5"
    assert "people" not in provider_schema(DraftBacklogV3)["properties"]
    assert "draft-v5" not in DRAFT_PROMPTS, (
        "that name belongs to an experiment that was not adopted"
    )


def test_agent_runs_draft_with_the_people_prompt_and_schema() -> None:
    assert DRAFT_PROMPT == "draft-v6"
    assert AGENT_SCHEMA_VERSION == PROMPT_SCHEMAS["draft-v6"] == "draft-backlog.v4"
    assert PROMPT_CHECKS["draft-v6"] == PEOPLE_CHECKS
    assert DRAFT_PROMPTS["draft-v6"].startswith(DRAFT_PROMPTS["draft-v4"])


def test_schema_rejects_duplicate_person_refs() -> None:
    with pytest.raises(ValidationError, match="Person refs must be unique"):
        DraftBacklogV4.model_validate(_draft(_person(), _person(name="Sam Okafor")))


def test_an_over_long_people_section_does_not_invalidate_the_draft() -> None:
    long = _person(said="word " * 200)
    crowd = [_person(f"P{n}", name=f"Person {n}") for n in range(2, MAX_PEOPLE_PER_RUN + 4)]

    draft = DraftBacklogV4.model_validate(_draft(long, *crowd))

    assert len(draft.people) > MAX_PEOPLE_PER_RUN


def test_stored_drafts_of_every_schema_version_still_load() -> None:
    v3 = {key: value for key, value in _draft().items() if key != "people"}
    v3["questions"] = [
        {"subject": "s", "question": "?", "why_it_matters": "!", "citations": [BOOK], "affects": []}
    ]

    assert type(parse_draft(_draft(_person()))) is DraftBacklogV4
    assert type(parse_draft(v3)) is DraftBacklogV3


def test_v6_requests_limit_person_citations_and_refs_and_stay_strict() -> None:
    schema = constrain_ids(provider_schema(DraftBacklogV4), ["B1", "B2"])
    person = schema["properties"]["people"]["items"]["properties"]

    assert person["citations"]["items"]["properties"]["block_id"]["enum"] == ["B1", "B2"]
    assert person["rights_citations"]["items"]["properties"]["block_id"]["enum"] == ["B1", "B2"]
    assert person["ref"]["enum"] == [f"P{n}" for n in range(1, MAX_PEOPLE_PER_RUN + 1)]
    assert schema["properties"]["people"]["maxItems"] == MAX_PEOPLE_PER_RUN
    assert strict_schema(schema)[1], "every property required, so strict decoding applies"
    assert strict_schema(constrain_ids(provider_schema(DraftPatchV4), ["B1"]))[1]


def test_a_v6_draft_request_leaves_room_for_output_on_the_backup_provider() -> None:
    """The people section must not crowd a draft out of the backup's per-request allowance.

    Twenty-seven paragraphs of 30 words is about the size of the dev packs' sources.
    """
    blocks = [SourceBlockInput(f"B{n}", "transcript paragraph", "word " * 30) for n in range(1, 28)]
    schema = constrain_ids(provider_schema(DraftBacklogV4), [block.id for block in blocks])
    request = ModelRequest(
        system_instruction=DRAFT_PROMPTS["draft-v6"],
        history=(UserMessage(sources_message(blocks, "Draft the backlog as JSON.", "draft-v6")),),
        max_output_tokens=8000,
        output_schema=schema,
    )
    free_tier = groq.PROFILE.free_tier
    assert free_tier is not None

    body = build_request_body(
        request,
        groq.PROFILE.default_model,
        "low",
        cap=groq.PROFILE.max_output_tokens_cap,
        request_token_limit=free_tier.tokens_per_minute,
    )

    assert body["max_completion_tokens"] >= 1500


def test_a_person_problem_is_repaired_with_a_patch_of_that_person() -> None:
    uncited = json.dumps(_draft(_person(rights="decides")))
    fixed = _person(rights="decides", rights_citations=[CONFIRMS])
    provider = ScriptedProvider([_result(uncited), _result(_patch(fixed))])

    outcome = draft_single_pass(provider, BLOCKS, max_output_tokens=100, prompt="draft-v6")

    assert (outcome.repair, outcome.repaired, outcome.check_problems) == ("targeted", True, ())
    assert outcome.repair_triggers == ("stated_right_without_citation",)
    assert isinstance(outcome.draft, DraftBacklogV4)
    assert [(p.ref, p.rights, len(p.rights_citations)) for p in outcome.draft.people] == [
        ("P1", "decides", 1)
    ]
    repair = provider.requests[1]
    assert "- person P1 has rights 'decides' with no citation" in str(repair.history[2])
    assert "people you add or change" in str(repair.history[2])
    patch_schema = cast(dict[str, Any], repair.output_schema)
    assert set(patch_schema["properties"]) == {"statements", "items", "questions", "people"}


def test_a_person_problem_the_repair_leaves_is_reported_on_the_draft() -> None:
    invented = json.dumps(_draft(_person(name="Morgan Vale")))
    provider = ScriptedProvider([_result(invented), _result(_patch())])

    outcome = draft_single_pass(provider, BLOCKS, max_output_tokens=100, prompt="draft-v6")

    assert outcome.draft is not None
    assert (outcome.repair, outcome.repaired) == ("targeted", False)
    assert outcome.repair_triggers == ("person_not_named",)
    assert outcome.check_problems[0].startswith("person P1 'Morgan Vale' is not named")


def test_a_patch_replaces_a_person_by_ref_and_adds_new_ones() -> None:
    draft = DraftBacklogV4.model_validate(_draft(_person(), _person("P2", name="Sam Okafor")))
    patch = DraftPatchV4.model_validate_json(
        _patch(_person("P2", name="Sam", role=""), _person("P3", name="Alex"))
    )

    patched = apply_patch(draft, patch)

    assert isinstance(patched, DraftBacklogV4)
    assert [(p.ref, p.name) for p in patched.people] == [
        ("P1", "Dana Ruiz"),
        ("P2", "Sam"),
        ("P3", "Alex"),
    ]


def _people(*people: dict[str, Any]) -> list[tuple[str, str, int, int]]:
    extracted = to_people(DraftBacklogV4.model_validate(_draft(*people)), PASSAGES)
    assert [extraction_problems(person) for person in extracted] == [[] for _ in extracted]
    return [
        (person.name, person.stated_rights, len(person.evidence), len(person.rights_evidence))
        for person in extracted
    ]


def test_people_become_stored_passages_with_their_stated_rights() -> None:
    extracted = to_people(
        DraftBacklogV4.model_validate(
            _draft(_person(rights="decides", rights_citations=[CONFIRMS]))
        ),
        PASSAGES,
    )

    (dana,) = extracted
    assert (dana.name, dana.role, dana.stated_rights) == (
        "Dana Ruiz",
        "Facilities Manager",
        "decides",
    )
    assert [(e.block_id, e.quote) for e in dana.evidence] == [
        (PASSAGES["B2"].block_id, NAMED["quote"]),
        (PASSAGES["B3"].block_id, SAID["quote"]),
    ]
    assert [(e.block_id, e.quote) for e in dana.rights_evidence] == [
        (PASSAGES["B4"].block_id, CONFIRMS["quote"])
    ]


@pytest.mark.parametrize(
    ("person", "kept"),
    [
        (_person(citations=[]), []),
        (_person(name="Morgan Vale"), []),
        (_person(citations=[{"block_id": "B2", "quote": "Dana Ruiz, the director"}]), []),
        (_person(citations=[{"block_id": "A1", "quote": "Dana Ruiz decides"}]), []),
        (_person(name="x" * 81), []),
        (_person(rights="decides"), [("Dana Ruiz", "not_stated", 2, 0)]),
        (
            _person(
                rights="decides", rights_citations=[{"block_id": "B4", "quote": "Dana decides"}]
            ),
            [("Dana Ruiz", "not_stated", 2, 0)],
        ),
        (
            _person(
                rights="decides",
                rights_citations=[{"block_id": "A1", "quote": "Dana Ruiz decides"}],
            ),
            [("Dana Ruiz", "not_stated", 2, 0)],
        ),
        (_person(rights_citations=[CONFIRMS]), [("Dana Ruiz", "not_stated", 2, 0)]),
        (_person(citations=[NAMED, SAID, CONFIRMS]), [("Dana Ruiz", "not_stated", 2, 0)]),
        (
            _person(citations=[SAID, {"block_id": "B2", "quote": "Dana Ruiz, the director"}]),
            [],
        ),
    ],
)
def test_code_keeps_only_people_and_rights_a_pinned_passage_supports(
    person: dict[str, Any], kept: list[tuple[str, str, int, int]]
) -> None:
    assert _people(person) == kept


def test_people_are_trimmed_deduplicated_and_capped() -> None:
    wordy = _person(said="word " * 200, name="  Dana   Ruiz ")
    again = _person("P2", name="dana ruiz", role="Someone else")
    named = "Attendees: " + ", ".join(f"Person {n}" for n in range(1, 20))
    passages = PASSAGES | {
        "B5": Passage(SourceBlockId(UUID(int=20)), VERSION, "transcript", 5, named)
    }
    crowd = [
        _person(
            f"P{n + 2}", name=f"Person {n}", citations=[{"block_id": "B5", "quote": "Attendees"}]
        )
        for n in range(1, 15)
    ]

    extracted = to_people(DraftBacklogV4.model_validate(_draft(wordy, again, *crowd)), passages)

    assert len(extracted) == MAX_PEOPLE_PER_RUN
    assert (extracted[0].name, extracted[0].role) == ("Dana Ruiz", "Facilities Manager")
    assert len(extracted[0].said) == MAX_SAID_CHARS
    assert extracted[0].said.endswith("…")
    assert [person.name for person in extracted[1:3]] == ["Person 1", "Person 2"]


def test_an_over_long_quote_cites_the_whole_paragraph_instead() -> None:
    long_text = "Dana Ruiz said: " + "word " * 100
    passages = {"B1": Passage(SourceBlockId(UUID(int=11)), VERSION, "transcript", 1, long_text)}
    person = _person(citations=[{"block_id": "B1", "quote": long_text}])

    (dana,) = to_people(DraftBacklogV4.model_validate(_draft(person)), passages)

    assert len(long_text) > MAX_QUOTE_CHARS
    assert [e.quote for e in dana.evidence] == [None]


def test_the_paragraph_that_names_a_person_survives_the_evidence_limit() -> None:
    person = _person(citations=[SAID, CONFIRMS, NAMED])

    (dana,) = to_people(DraftBacklogV4.model_validate(_draft(person)), PASSAGES)

    assert [e.block_id for e in dana.evidence] == [PASSAGES["B2"].block_id, PASSAGES["B3"].block_id]
