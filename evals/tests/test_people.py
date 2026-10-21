"""Expected people in a pack and how a draft's people are scored. All names are synthetic."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from scopesteps.agent.client import (
    DraftBacklogV4,
    DraftBacklogV5,
    ModelRequest,
    ModelResult,
    ModelTurn,
    Usage,
    parse_draft,
    participants_of,
)
from scopesteps.evals.annotations import ExpectedPerson
from scopesteps.evals.packs import DATASETS_DIR, Pack, PackError, load_pack, load_packs
from scopesteps.evals.runner import (
    DraftSettings,
    Pacer,
    rescore_report,
    review_sheet,
    run_single_pass,
    summarize,
    write_report,
)
from scopesteps.evals.scoring import PackInputs, build_inputs, score_draft

PackFactory = Callable[..., Path]
NAMED = {"file": "transcript.md", "paragraph": 2, "quote": "Dana Ruiz"}
STATED = {"file": "transcript.md", "paragraph": 15, "quote": "until Dana confirms"}


@pytest.fixture(scope="module")
def campus() -> Pack:
    return load_pack(DATASETS_DIR / "dev" / "campus-room-booking", "dev")


def _expected(**changes: Any) -> dict[str, Any]:
    return {"name": "Dana Ruiz", "role": "Facilities Manager", "evidence": [NAMED]} | changes


@pytest.mark.parametrize(
    ("person", "message"),
    [
        (_expected(evidence=[]), "at least 1 item"),
        (_expected(rights="decides"), "rights_evidence is needed"),
        (_expected(rights_evidence=[STATED]), "rights_evidence is needed"),
        (_expected(rights="owns"), "Input should be"),
        (
            _expected(evidence=[{"file": "change_request.txt", "paragraph": 1, "quote": "x"}]),
            "initial sources",
        ),
    ],
)
def test_invalid_expected_people_are_rejected(person: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ExpectedPerson.model_validate(person)


def _pack_with(people: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "pack": {"id": "demo", "title": "Demo", "summary": "Demo pack"},
        "annotations": [
            {
                "id": "CR-01",
                "kind": "confirmed_requirement",
                "statement": "Users can book a room.",
                "expect": "include",
                "evidence": [{"file": "brief.md", "paragraph": 2, "quote": "book a room"}],
            }
        ],
        "people": people,
    }


BRIEF = "# Brief\n\nUsers can book a room. Sponsor: Dana Ruiz.\n"
IN_BRIEF = {"file": "brief.md", "paragraph": 2, "quote": "Sponsor: Dana Ruiz."}


def test_a_pack_without_people_is_still_valid(make_pack: PackFactory) -> None:
    assert load_pack(make_pack(), "dev").annotations.people == []


def test_a_pack_lists_the_people_its_sources_name(make_pack: PackFactory) -> None:
    annotations = _pack_with([{"name": "Dana Ruiz", "role": "Sponsor", "evidence": [IN_BRIEF]}])

    pack = load_pack(make_pack(brief=BRIEF, annotations=annotations), "dev")

    assert [(p.name, p.rights) for p in pack.annotations.people] == [("Dana Ruiz", "not_stated")]


@pytest.mark.parametrize(
    ("people", "problem"),
    [
        (
            [{"name": "Dana Ruiz", "evidence": [IN_BRIEF | {"quote": "Sponsor: D. Ruiz"}]}],
            "Dana Ruiz: quote not found in brief.md paragraph 2",
        ),
        (
            [{"name": "Dana Ruiz", "evidence": [IN_BRIEF | {"paragraph": 9}]}],
            "Dana Ruiz: brief.md has no paragraph 9",
        ),
        (
            [{"name": "Morgan Vale", "evidence": [IN_BRIEF]}],
            "Morgan Vale: no evidence paragraph names them",
        ),
        (
            [
                {"name": "Dana Ruiz", "evidence": [IN_BRIEF]},
                {"name": "dana  ruiz", "evidence": [IN_BRIEF]},
            ],
            "Duplicate people",
        ),
    ],
)
def test_expected_people_are_checked_against_the_sources(
    make_pack: PackFactory, people: list[dict[str, Any]], problem: str
) -> None:
    with pytest.raises(PackError, match=problem):
        load_pack(make_pack(brief=BRIEF, annotations=_pack_with(people)), "dev")


def test_the_dev_packs_list_people_with_synthetic_names() -> None:
    people = {pack.id: pack.annotations.people for pack in load_packs("dev")}

    assert {pack: [(p.name, p.rights) for p in listed] for pack, listed in people.items()} == {
        "campus-room-booking": [
            ("Dana Ruiz", "decides"),
            ("Sam Okafor", "not_stated"),
            ("Priya Nair", "not_stated"),
            ("Alex Kim", "not_stated"),
        ],
        "makerspace-tool-library": [
            ("Jordan Lee", "not_stated"),
            ("Mei Chen", "not_stated"),
            ("Tom Baker", "not_stated"),
        ],
        "youth-football-registration": [
            ("Priya Nair", "not_stated"),
            ("Marcus Hale", "not_stated"),
            ("Ellen Brooks", "not_stated"),
            ("Jonah Kim", "not_stated"),
        ],
    }


# Each person's first turn in the campus transcript, which names them through the pack's
# confirmed speakers (speakers.yaml).
FIRST_TURNS = {
    "Dana Ruiz": (4, "The main thing for us is"),
    "Sam Okafor": (6, "Students mostly want a room for"),
    "Priya Nair": (5, "The booking service will reject an"),
    "Alex Kim": (3, "Thanks for coming. Today we agree"),
}


def _cite(inputs: PackInputs, paragraph: int, quote: str) -> dict[str, str]:
    return {"block_id": inputs.block_ids_by_paragraph[("transcript.md", paragraph)], "quote": quote}


def _person(inputs: PackInputs, ref: str, name: str, **changes: Any) -> dict[str, Any]:
    person: dict[str, Any] = {
        "ref": ref,
        "name": name,
        "role": "",
        "said": "",
        "citations": [_cite(inputs, *FIRST_TURNS.get(name, (2, name)))],
        "rights": "not_stated",
        "rights_citations": [],
    }
    return person | changes


def _draft(*people: dict[str, Any]) -> DraftBacklogV4:
    return DraftBacklogV4.model_validate(
        {"statements": [], "items": [], "questions": [], "people": list(people)}
    )


def _key_answers(inputs: PackInputs) -> list[dict[str, Any]]:
    confirms = _cite(inputs, 15, "stay open until Dana confirms")
    return [
        _person(inputs, "P1", "Dana Ruiz", rights="decides", rights_citations=[confirms]),
        _person(inputs, "P2", "Sam Okafor"),
        _person(inputs, "P3", "Priya Nair"),
        _person(inputs, "P4", "Alex Kim"),
    ]


def test_a_draft_that_lists_every_person_with_the_stated_rights_scores_in_full(
    campus: Pack,
) -> None:
    inputs = build_inputs(campus, "initial")

    card = score_draft(campus, inputs, _draft(*_key_answers(inputs)))

    assert (card.people_expected, card.people_found, card.people_unexpected) == (4, 4, 0)
    assert (card.rights_correct, card.rights_overclaimed) == (4, 0)
    assert card.citation_accuracy == 1, "people citations count like any other"


def test_missing_invented_and_overclaimed_people_are_counted(campus: Pack) -> None:
    inputs = build_inputs(campus, "initial")
    said = _cite(inputs, 4, "ending double bookings")
    draft = _draft(
        _person(inputs, "P1", "Dana", citations=[said]),
        _person(inputs, "P2", "Sam Okafor", rights="advises", rights_citations=[said]),
        _person(inputs, "P3", "Priya Nair", citations=[_cite(inputs, 2, "Priya the developer")]),
        _person(inputs, "P4", "Facilities Office", citations=[said]),
    )

    card = score_draft(campus, inputs, draft)

    found = {person.name: person for person in card.people if person.expected}
    assert (found["Dana Ruiz"].found, found["Dana Ruiz"].rights_drafted) == (True, "not_stated")
    assert found["Priya Nair"].found is False, "a quote that is not in the block names nobody"
    assert found["Alex Kim"].found is False
    assert (card.people_expected, card.people_found) == (4, 2)
    assert [p.name for p in card.people if not p.expected] == ["Facilities Office"]
    assert card.people_unexpected == 1
    assert (card.rights_correct, card.rights_overclaimed) == (0, 1), (
        "Dana's stated right was missed and Sam was given one no source states"
    )


def test_a_drafted_right_without_a_citation_that_holds_does_not_count(campus: Pack) -> None:
    inputs = build_inputs(campus, "initial")
    people = _key_answers(inputs)
    people[0]["rights_citations"] = [_cite(inputs, 15, "Dana decides everything")]

    card = score_draft(campus, inputs, _draft(*people))

    dana = next(person for person in card.people if person.name == "Dana Ruiz")
    assert (dana.rights_expected, dana.rights_drafted) == ("decides", "uncited")
    assert card.rights_correct == 3


def test_drafts_from_earlier_prompts_are_not_scored_on_people(campus: Pack) -> None:
    inputs = build_inputs(campus, "initial")

    card = score_draft(
        campus, inputs, parse_draft({"statements": [], "items": [], "questions": []})
    )

    assert card.people == []


class _Scripted:
    def __init__(self, text: str) -> None:
        self.text = text

    def generate(self, request: ModelRequest) -> ModelResult:
        return ModelResult(
            "test", "m", ModelTurn(()), self.text, (), "completed", Usage(total_tokens=7), 100
        )


def test_a_v6_run_reports_people_and_rescoring_reproduces_them(
    campus: Pack, tmp_path: Path
) -> None:
    inputs = build_inputs(campus, "initial")
    people = _key_answers(inputs)[:3]
    people[1] = people[1] | {"rights": "decides", "rights_citations": people[0]["rights_citations"]}
    draft = {"statements": [], "items": [], "questions": [], "people": people}

    records = run_single_pass(
        _Scripted(json.dumps(draft)),
        [campus],
        ["initial"],
        repeats=2,
        max_output_tokens=10,
        pacer=Pacer(15, 10, sleep=lambda _: None, clock=lambda: 0.0, log=lambda _: None),
        settings=DraftSettings(prompt="draft-v6", run_checks=False),
    )

    summary = summarize(records)["initial"]
    assert (summary["people_found_count"], summary["rights_correct_count"]) == ("6/8", "4/6")
    assert (summary["people_unexpected"], summary["rights_overclaimed"]) == (0, 2)
    assert summary["people_found_ci95"] == "41%-93%"
    assert "| Dana Ruiz | yes | yes | decides | decides |" in review_sheet(records)
    assert "| Alex Kim | yes | no | not_stated |  |" in review_sheet(records)

    json_path, _ = write_report(
        records, model_id="m", split="dev", configuration={}, directory=tmp_path
    )
    report = json.loads(json_path.read_text())
    assert report["schema_version"] == ["draft-backlog.v4"]
    rescore_report(json_path, [campus])
    assert json.loads(json_path.read_text())["summary"] == report["summary"]


def test_earlier_prompts_report_no_people_metrics(campus: Pack) -> None:
    records = run_single_pass(
        _Scripted(json.dumps({"statements": [], "items": [], "questions": []})),
        [campus],
        ["initial"],
        repeats=1,
        max_output_tokens=10,
        pacer=Pacer(15, 10, sleep=lambda _: None, clock=lambda: 0.0, log=lambda _: None),
        settings=DraftSettings(run_checks=False),
    )

    assert not any(key.startswith(("people", "rights")) for key in summarize(records)["initial"])
    assert "## People" not in review_sheet(records)


def test_participants_named_by_id_are_found_under_their_confirmed_names(campus: Pack) -> None:
    inputs = build_inputs(campus, "initial")
    participants = participants_of(block.speakers for block in inputs.blocks)
    by_name = {note.name: speaker for speaker, note in participants.notes.items()}
    confirms = _cite(inputs, 15, "stay open until Dana confirms")
    people = [
        _person(inputs, f"P{index}", "someone", citations=[], speaker=by_name[name])
        | ({"rights": "decides", "rights_citations": [confirms]} if name == "Dana Ruiz" else {})
        for index, name in enumerate(("Dana Ruiz", "Sam Okafor", "Priya Nair", "Alex Kim"), 1)
    ]
    draft = DraftBacklogV5.model_validate(
        {"statements": [], "items": [], "questions": [], "people": people}
    )

    card = score_draft(campus, inputs, draft)

    assert (card.people_expected, card.people_found, card.people_unexpected) == (4, 4, 0)
    assert (card.rights_correct, card.rights_overclaimed) == (4, 0)
