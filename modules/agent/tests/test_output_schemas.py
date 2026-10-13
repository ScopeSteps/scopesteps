import json
from typing import Any

import pytest
from pydantic import ValidationError

from scopesteps.agent.application.schemas import DraftBacklogV1 as DraftBacklog
from scopesteps.agent.application.schemas import LookupSourceArgs, provider_schema

CITATION = {"block_id": "B8", "quote": "book an individual one-off slot"}


def _item(ref: str, kind: str, parent: str | None, **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "ref": ref,
        "kind": kind,
        "parent_ref": parent,
        "title": f"Item {ref}",
        "description": "",
        "criteria": [],
        "assumptions": [],
        "open_questions": [],
    }
    return item | overrides


def _draft(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"statements": [], "items": items, "questions": []}


def test_valid_draft_is_accepted() -> None:
    draft = DraftBacklog.model_validate(
        _draft(
            [
                _item("E1", "epic", None),
                _item(
                    "S1",
                    "story",
                    "E1",
                    criteria=[{"text": "Book a slot", "origin": "source", "citations": [CITATION]}],
                ),
            ]
        )
    )

    assert [item.ref for item in draft.items] == ["E1", "S1"]


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ([_item("S1", "story", None)], "must belong to an epic"),
        ([_item("E1", "epic", "E2")], "cannot have a parent"),
        ([_item("E1", "epic", None), _item("E1", "epic", None)], "unique"),
        ([_item(f"E{i}", "epic", None) for i in range(1, 4)], "At most 2 epics"),
        (
            [_item("E1", "epic", None)] + [_item(f"S{i}", "story", "E1") for i in range(1, 10)],
            "At most 2 epics and 8 stories",
        ),
        (
            [
                _item("E1", "epic", None),
                _item(
                    "S1",
                    "story",
                    "E1",
                    criteria=[{"text": "x", "origin": "source", "citations": []}],
                ),
            ],
            "sourced criterion needs a citation",
        ),
        ([_item("X1", "epic", None)], "pattern"),
    ],
)
def test_invalid_drafts_are_rejected(items: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        DraftBacklog.model_validate(_draft(items))


@pytest.mark.parametrize(
    ("args", "valid"),
    [
        ({"query": "cancel"}, True),
        ({"block_ids": ["B1"]}, True),
        ({}, False),
        ({"query": "  "}, False),
        ({"query": "x", "limit": 11}, False),
        ({"query": "x", "unknown": 1}, False),
    ],
)
def test_lookup_source_arguments(args: dict[str, Any], valid: bool) -> None:
    if valid:
        LookupSourceArgs.model_validate(args)
    else:
        with pytest.raises(ValidationError):
            LookupSourceArgs.model_validate(args)


def test_provider_schema_inlines_refs_and_keeps_fields_named_title() -> None:
    schema = provider_schema(DraftBacklog)
    text = json.dumps(schema)

    assert "$ref" not in text
    assert "$defs" not in text
    item_properties = schema["properties"]["items"]["items"]["properties"]
    assert "title" in item_properties
    assert "title" not in item_properties["title"]
