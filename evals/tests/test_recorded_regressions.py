"""Offline regression: real recorded drafts must keep their verdicts as scoring and checks evolve.

If a deliberate rule change alters a verdict, regenerate the fixture and explain why in the PR.
The drafts are scored against the packs as they were recorded with (`fixtures/recorded/packs`):
the dev packs later dropped their attendee lists and inline roles (ADR 0012), which the recorded
quotes still contain.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from scopesteps.agent.client import PROMPT_CHECKS, check_draft, parse_draft, requirement_blocks
from scopesteps.evals.packs import Pack, load_packs
from scopesteps.evals.scoring import build_inputs, score_draft

RECORDED = Path(__file__).resolve().parents[1] / "fixtures" / "recorded"
FIXTURES = sorted(RECORDED.glob("*.json"))
CASES: list[dict[str, Any]] = [
    case for path in FIXTURES for case in json.loads(path.read_text(encoding="utf-8"))["cases"]
]


@pytest.fixture(scope="module")
def packs() -> dict[str, Pack]:
    return {pack.id: pack for pack in load_packs("dev", root=RECORDED / "packs")}


@pytest.mark.parametrize(
    "case", CASES, ids=[f"{c['prompt_version'][:8]}-{c['pack']}-{c['mode']}" for c in CASES]
)
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


@pytest.mark.parametrize("prompt", ["draft-v2", "draft-v3", "draft-v4"])
def test_fixtures_cover_both_packs_and_modes(prompt: str) -> None:
    assert {(c["pack"], c["mode"]) for c in CASES if c["prompt_version"].startswith(prompt)} == {
        ("campus-room-booking", "initial"),
        ("campus-room-booking", "with_answers"),
        ("makerspace-tool-library", "initial"),
        ("makerspace-tool-library", "with_answers"),
    }
