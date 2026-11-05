"""A draft built from Word, PDF and WebVTT sources is cited, approved and exported exactly as
one built from text files (ADR 0025). The agent is a scripted provider: no live model calls.
The sources are the synthetic samples in `samples/sources`."""

import csv
import io
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from scopesteps.agent.client import RunLimits
from scopesteps.agent.domain.model import ModelResult, ModelTurn, Usage
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.api.seed import DEMO_PROJECT_ID

SAMPLES = Path(__file__).resolve().parents[3] / "samples/sources/valid"
PROJECT_URL = f"/api/v1/projects/{DEMO_PROJECT_ID}"
MODEL = "gemini-3.5-flash-lite"
LIMITS = RunLimits(
    max_turns=6, max_tool_calls=8, max_output_tokens_per_call=8000, max_total_tokens=200_000
)
Json = dict[str, Any]

SLOT = "A resident can book one 45-minute slot per Saturday."
PAYMENTS = "Out of scope: payments for parts and recurring bookings."
CALLS = "Half the calls I get are people asking whether there is space."
STAND = "Stand: Stand 1 | Open: Every Saturday"


def _result(text: str) -> ModelResult:
    return ModelResult(
        provider="test",
        model_id=MODEL,
        turn=ModelTurn(({"type": "model_output", "text": text},)),
        text=text,
        tool_calls=(),
        finish_reason="completed",
        usage=Usage(input_tokens=1000, output_tokens=100, total_tokens=1100),
        latency_ms=50,
    )


def _upload(client: TestClient) -> list[Json]:
    files = [
        ("brief", ("brief.pdf", (SAMPLES / "brief.pdf").read_bytes())),
        ("transcript", ("transcript.vtt", (SAMPLES / "transcript.vtt").read_bytes())),
        ("supporting_document", ("brief.docx", (SAMPLES / "brief.docx").read_bytes())),
    ]
    response = client.post(
        f"{PROJECT_URL}/sources", files=files, headers={"Idempotency-Key": "upload-key-0001"}
    )
    assert response.status_code == 201, response.text
    versions: list[Json] = response.json()["source_versions"]
    return versions


def _labels(client: TestClient, versions: list[Json]) -> list[tuple[str, str]]:
    """Each paragraph's text with the label the run gives it: B1, B2, ... across the pinned
    versions. Two files may hold the same paragraph, so this is a list, not a mapping."""
    texts = [
        block["text"]
        for version in versions
        for block in client.get(f"{PROJECT_URL}/sources/{version['id']}/blocks").json()
    ]
    return [(text, f"B{index}") for index, text in enumerate(texts, start=1)]


def _cite(labels: list[tuple[str, str]], paragraph: str, quote: str) -> Json:
    """A citation of `quote` in the paragraph that starts with `paragraph`."""
    label = next(label for text, label in labels if text.startswith(paragraph))
    return {"block_id": label, "quote": quote}


def _draft(labels: list[tuple[str, str]]) -> str:
    slot = _cite(labels, SLOT, SLOT)
    stand = _cite(labels, STAND, "Stand 1 | Open: Every Saturday")
    calls = _cite(labels, "Tomas Reed: " + CALLS, CALLS)
    return json.dumps(
        {
            "statements": [
                {"id": "T1", "kind": "confirmed", "summary": "Book a slot", "citations": [slot]},
                {
                    "id": "T2",
                    "kind": "exclusion",
                    "summary": "No payments",
                    "citations": [_cite(labels, PAYMENTS, "payments for parts")],
                },
                {"id": "T3", "kind": "context", "summary": "Calls", "citations": [calls]},
                # The draft check wants every paragraph classified; the rest are context.
                {
                    "id": "T4",
                    "kind": "context",
                    "summary": "Background",
                    "citations": [
                        {"block_id": label, "quote": text}
                        for text, label in labels
                        if not text.startswith((SLOT, PAYMENTS, "Tomas Reed: " + CALLS))
                    ],
                },
            ],
            "items": [
                {
                    "ref": "E1",
                    "kind": "epic",
                    "parent_ref": None,
                    "title": "Workshop booking",
                    "description": "Residents book repair slots.",
                    "criteria": [
                        {"text": "Residents book slots.", "origin": "source", "citations": [slot]}
                    ],
                    "assumptions": [],
                    "open_questions": [],
                    "covers": [],
                },
                {
                    "ref": "S1",
                    "kind": "story",
                    "parent_ref": "E1",
                    "title": "Book a repair slot",
                    "description": "As a resident, I want to book a slot, so that a stand is free.",
                    "criteria": [
                        {
                            "text": "One 45-minute slot per Saturday.",
                            "origin": "source",
                            "citations": [slot],
                        },
                        {
                            "text": "Stand 1 opens every Saturday.",
                            "origin": "source",
                            "citations": [stand],
                        },
                    ],
                    "assumptions": [],
                    "open_questions": [],
                    "covers": ["T1"],
                },
            ],
            "questions": [],
            "people": [
                {
                    "ref": "P1",
                    "name": "Tomas Reed",
                    "role": "",
                    "said": "Gets calls asking whether there is space.",
                    "citations": [calls],
                    "rights": "not_stated",
                    "rights_citations": [],
                    "speaker": "",
                }
            ],
        }
    )


def test_a_draft_from_word_pdf_and_webvtt_sources_is_cited_approved_and_exported(
    client: TestClient, confirm_speakers: Callable[[TestClient], None]
) -> None:
    pdf, vtt, word = versions = _upload(client)
    confirm_speakers(client)
    labels = _labels(client, versions)
    client.app.state.agent_runtime = replace(  # type: ignore[attr-defined]
        client.app.state.agent_runtime,  # type: ignore[attr-defined]
        provider_name="gemini",
        model_id=MODEL,
        limits=LIMITS,
        provider=ScriptedProvider([_result("READY"), _result(_draft(labels))]),
    )

    created = client.post(
        f"{PROJECT_URL}/runs",
        json={"mode": "initial", "source_version_ids": [v["id"] for v in versions]},
        headers={"Idempotency-Key": "run-key-0001"},
    )
    run_id = created.json()["id"]
    client.post(f"/api/v1/runs/{run_id}/advance", headers={"Idempotency-Key": "advance-0001"})
    ready = client.post(
        f"/api/v1/runs/{run_id}/advance", headers={"Idempotency-Key": "advance-0002"}
    ).json()
    assert (ready["status"], ready["problems"]) == ("ready_for_review", [])

    draft = client.get(
        f"/api/v1/projects/{DEMO_PROJECT_ID}/backlogs/{ready['candidate_version_id']}"
    ).json()
    story = draft["items"][1]
    cited = {(e["source_version_id"], e["quote"]) for c in story["criteria"] for e in c["evidence"]}
    assert cited == {(pdf["id"], SLOT), (word["id"], "Stand 1 | Open: Every Saturday")}
    assert vtt["media_type"] == "text/vtt"

    approved = client.post(
        f"/api/v1/backlogs/{draft['id']}/approve",
        json={
            "expected_revision": draft["revision"],
            "content_hash": draft["content_hash"],
            "expected_baseline_id": None,
        },
        headers={"Idempotency-Key": "approve-0001"},
    )
    assert approved.status_code == 200, approved.text

    exported = client.get(f"/api/v1/backlogs/{draft['id']}/export", params={"format": "json"})
    csv_export = client.get(f"/api/v1/backlogs/{draft['id']}/export", params={"format": "csv"})
    assert exported.status_code == 200, exported.text
    body = exported.json()
    assert body["version"]["state"] == "approved"
    assert set(body["version"]["source_version_ids"]) == {v["id"] for v in versions}
    assert body["withheld_evidence_count"] == 0
    rows = list(csv.reader(io.StringIO(csv_export.content.decode("utf-8"), newline="")))
    assert rows[2][:3] == ["2", "Story", "Book a repair slot"]
    assert "- Stand 1 opens every Saturday." in rows[2][3]
