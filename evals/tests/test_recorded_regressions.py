"""Offline regression: real recorded drafts must keep their verdicts as scoring and checks evolve.

If a deliberate rule change alters a verdict, regenerate the fixture and explain why in the PR.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from scopesteps.agent.client import PROMPT_CHECKS, check_draft, parse_draft, requirement_blocks
from scopesteps.evals.packs import Pack, load_packs
from scopesteps.evals.scoring import build_inputs, score_draft

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "v2-dev-drafts.json"
CASES: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


@pytest.fixture(scope="module")
def packs() -> dict[str, Pack]:
    return {pack.id: pack for pack in load_packs("dev")}


@pytest.mark.parametrize("case", CASES, ids=[f"{c['pack']}-{c['mode']}" for c in CASES])
def test_recorded_drafts_keep_their_verdicts(case: dict[str, Any], packs: dict[str, Pack]) -> None:
    pack = packs[case["pack"]]
    inputs = build_inputs(pack, case["mode"])
    draft = parse_draft(case["draft"])
    prompt = case["prompt_version"].split("+")[0]
    answers = set(inputs.answer_block_by_annotation.values())

    card = score_draft(pack, inputs, draft)

    assert {r.annotation_id: r.verdict for r in card.results} == case["expected_verdicts"]
    assert card.citation_accuracy == case["expected_citation_accuracy"]
    assert (
        check_draft(
            draft,
            inputs.blocks,
            open_decision_blocks=inputs.open_decision_blocks,
            answer_blocks=answers,
            account_blocks=requirement_blocks(
                inputs.blocks, exclude={*inputs.open_decision_blocks, *answers}
            ),
            enabled=PROMPT_CHECKS[prompt],
        )
        == case["expected_check_problems"]
    )


def test_fixture_covers_both_packs_and_modes() -> None:
    assert {(c["pack"], c["mode"]) for c in CASES} == {
        ("campus-room-booking", "initial"),
        ("campus-room-booking", "with_answers"),
        ("makerspace-tool-library", "initial"),
        ("makerspace-tool-library", "with_answers"),
    }
