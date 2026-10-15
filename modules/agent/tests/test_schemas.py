from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from scopesteps.agent.http.schemas import AnswerRequest, CreateRunRequest

SOURCES = [str(uuid4())]


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "initial", "source_version_ids": SOURCES},
        {
            "mode": "change",
            "base_version_id": str(uuid4()),
            "base_content_hash": "a" * 64,
            "request_text": "Add weekly recurring reservations",
        },
    ],
)
def test_create_run_accepts_valid_modes(payload: dict[str, Any]) -> None:
    assert CreateRunRequest.model_validate(payload).mode == payload["mode"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"mode": "initial", "source_version_ids": []}, "at least one source version"),
        ({"mode": "change", "source_version_ids": SOURCES}, "requires base_version_id"),
        (
            {
                "mode": "change",
                "source_version_ids": SOURCES,
                "base_version_id": str(uuid4()),
                "base_content_hash": "a" * 64,
                "request_text": "Add weekly bookings",
            },
            "pins its sources itself",
        ),
        (
            {"mode": "initial", "source_version_ids": SOURCES, "base_version_id": str(uuid4())},
            "takes no baseline",
        ),
        (
            {"mode": "initial", "source_version_ids": SOURCES, "request_text": "x" * 2001},
            "at most 2000",
        ),
    ],
)
def test_create_run_rejects_invalid_requests(payload: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        CreateRunRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("answer", "skip", "valid"),
    [
        ("Cancellations allowed until start", False, True),
        (None, True, True),
        (None, False, False),
        ("x", True, False),
    ],
)
def test_answer_requires_exactly_one_of_answer_or_skip(
    answer: str | None, skip: bool, valid: bool
) -> None:
    payload = {"question_id": str(uuid4()), "answer": answer, "skip": skip}

    if valid:
        AnswerRequest.model_validate(payload)
    else:
        with pytest.raises(ValidationError, match="exactly one of answer or skip"):
            AnswerRequest.model_validate(payload)
