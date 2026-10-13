"""Typed model outputs and tool arguments. The JSON schemas sent to providers come from here.

Output is untrusted: provider-side schema enforcement only guarantees JSON shape, so every
response is validated again with these models before anything is persisted.
"""

import copy
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SchemaName = Literal["draft-backlog.v1", "draft-backlog.v2"]
DRAFT_SCHEMA_VERSION: SchemaName = "draft-backlog.v2"
MAX_EPICS = 2
MAX_STORIES = 8


@dataclass(frozen=True)
class SourceBlockInput:
    """A citable passage shown to the model. `id` is what the model cites (B1, A1, ...)."""

    id: str
    label: str
    text: str


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(_Output):
    block_id: str = Field(description="ID of the source block, exactly as given, e.g. 'B12'.")
    quote: str = Field(min_length=1, description="Verbatim text copied from that block.")


class StatementV1(_Output):
    kind: Literal["confirmed", "exclusion", "proposal", "conflict", "open_question"]
    summary: str = Field(min_length=1)
    citations: list[Citation] = Field(min_length=1)


class Statement(_Output):
    """draft-backlog.v2: statements have ids so stories can trace to them."""

    id: str = Field(pattern=r"^T\d+$", description="T1, T2, ... unique within the draft.")
    kind: Literal["confirmed", "exclusion", "proposal", "conflict", "open_question", "context"]
    summary: str = Field(min_length=1)
    citations: list[Citation] = Field(min_length=1)


class DraftCriterion(_Output):
    text: str = Field(min_length=1)
    origin: Literal["source", "proposed"] = Field(
        description="'source' only when the citations state it; otherwise 'proposed'."
    )
    citations: list[Citation]


class DraftItemV1(_Output):
    ref: str = Field(pattern=r"^(E|S)\d+$", description="E1, E2 for epics; S1..S8 for stories.")
    kind: Literal["epic", "story"]
    parent_ref: str | None = Field(description="Epic ref for a story; null for an epic.")
    title: str = Field(min_length=1, max_length=200)
    description: str
    criteria: list[DraftCriterion]
    assumptions: list[str]
    open_questions: list[str]


class DraftItem(DraftItemV1):
    covers: list[str] = Field(
        description="Ids of the confirmed statements this item implements; empty for epics."
    )


class DraftQuestion(_Output):
    subject: str = Field(min_length=1)
    question: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    citations: list[Citation]


class QuestionPatch(_Output):
    """Targeted repair output: only the clarification questions a draft is missing."""

    questions: list[DraftQuestion] = Field(min_length=1, max_length=6)


def _check_items(items: Sequence[DraftItemV1]) -> None:
    refs = [item.ref for item in items]
    if len(refs) != len(set(refs)):
        raise ValueError("Item refs must be unique")
    epics = {item.ref for item in items if item.kind == "epic"}
    if len(epics) > MAX_EPICS or len(items) - len(epics) > MAX_STORIES:
        raise ValueError(f"At most {MAX_EPICS} epics and {MAX_STORIES} stories")
    for item in items:
        if item.kind == "epic" and item.parent_ref is not None:
            raise ValueError(f"Epic {item.ref} cannot have a parent")
        if item.kind == "story" and item.parent_ref not in epics:
            raise ValueError(f"Story {item.ref} must belong to an epic")
        for criterion in item.criteria:
            if criterion.origin == "source" and not criterion.citations:
                raise ValueError(f"{item.ref}: a sourced criterion needs a citation")


class DraftBacklogV1(_Output):
    """draft-backlog.v1, used by prompts draft-v1 and draft-v2. Kept for reproducibility."""

    statements: list[StatementV1]
    items: list[DraftItemV1] = Field(max_length=MAX_EPICS + MAX_STORIES)
    questions: list[DraftQuestion] = Field(max_length=6)

    @model_validator(mode="after")
    def check_structure(self) -> Self:
        _check_items(self.items)
        return self


class DraftBacklog(_Output):
    """draft-backlog.v2: adds statement ids, a context kind and item-to-statement traceability."""

    statements: list[Statement]
    items: list[DraftItem] = Field(max_length=MAX_EPICS + MAX_STORIES)
    questions: list[DraftQuestion] = Field(max_length=6)

    @model_validator(mode="after")
    def check_structure(self) -> Self:
        _check_items(self.items)
        ids = [statement.id for statement in self.statements]
        if len(ids) != len(set(ids)):
            raise ValueError("Statement ids must be unique")
        for item in self.items:
            unknown = sorted(set(item.covers) - set(ids))
            if unknown:
                raise ValueError(f"{item.ref} covers unknown statements {', '.join(unknown)}")
        return self


class PatchQuestion(DraftQuestion):
    replaces: int | None = Field(
        description="Number of the question this replaces (1 is the first), or null to add one."
    )


class DraftPatch(_Output):
    """Targeted repair output for draft-backlog.v2: only what changes, merged into the draft in
    code, so a repair costs a few hundred output tokens instead of a whole new draft."""

    statements: list[Statement] = Field(
        description="New statements, or existing ones rewritten in full under the same id."
    )
    items: list[DraftItem] = Field(
        description="New items, or existing ones rewritten in full under the same ref."
    )
    questions: list[PatchQuestion]


def apply_patch(draft: DraftBacklog, patch: DraftPatch) -> DraftBacklog:
    """Replace statements and items by id or ref, add new ones, then validate the whole draft."""
    statements = {statement.id: statement for statement in draft.statements}
    statements |= {statement.id: statement for statement in patch.statements}
    items = {item.ref: item for item in draft.items}
    items |= {item.ref: item for item in patch.items}
    questions = list(draft.questions)
    for patched in patch.questions:
        question = DraftQuestion.model_validate(patched.model_dump(exclude={"replaces"}))
        if patched.replaces is not None and 1 <= patched.replaces <= len(questions):
            questions[patched.replaces - 1] = question
        else:
            questions.append(question)
    return DraftBacklog.model_validate(
        {
            "statements": [statement.model_dump() for statement in statements.values()],
            "items": [item.model_dump() for item in items.values()],
            "questions": [question.model_dump() for question in questions],
        }
    )


AnyDraft = DraftBacklog | DraftBacklogV1
DRAFT_SCHEMAS: dict[SchemaName, type[DraftBacklog] | type[DraftBacklogV1]] = {
    "draft-backlog.v1": DraftBacklogV1,
    "draft-backlog.v2": DraftBacklog,
}


def parse_draft(data: object) -> AnyDraft:
    """Load a stored draft of either schema version (v2 drafts carry statement ids)."""
    try:
        return DraftBacklog.model_validate(data)
    except ValidationError:
        return DraftBacklogV1.model_validate(data)


MAX_QUESTIONS_PER_ROUND = 5


class ClarificationRequest(_Output):
    subject: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=1000)
    why_it_matters: str = Field(min_length=1, max_length=1000)
    block_ids: list[str] = Field(
        min_length=1, max_length=5, description="IDs of the source blocks the question is about."
    )


class RequestClarificationArgs(_Output):
    """Arguments of `request_clarification`. The run pauses until the reviewer answers or skips."""

    questions: list[ClarificationRequest] = Field(min_length=1, max_length=MAX_QUESTIONS_PER_ROUND)


class LookupSourceArgs(_Output):
    """Arguments of the read-only, project-scoped `lookup_source` tool."""

    query: str = Field(default="", description="Words to search for; empty when using block_ids.")
    block_ids: list[str] = Field(default=[], max_length=10, description="Exact block IDs to fetch.")
    limit: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def check_target(self) -> Self:
        if not self.query.strip() and not self.block_ids:
            raise ValueError("Provide a query or block_ids")
        return self


def provider_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema with $refs inlined and titles dropped, the subset providers accept reliably."""
    schema = model.model_json_schema()
    definitions: dict[str, Any] = schema.pop("$defs", {})

    def resolve(node: Any, *, property_map: bool = False) -> Any:
        if isinstance(node, dict):
            mapping = cast(dict[str, Any], node)
            if "$ref" in mapping:
                return resolve(definitions[str(mapping["$ref"]).rsplit("/", 1)[-1]])
            if property_map:  # Keys are field names, so a field called "title" must survive.
                return {key: resolve(value) for key, value in mapping.items()}
            return {
                key: resolve(value, property_map=key == "properties")
                for key, value in mapping.items()
                if key != "title"
            }
        if isinstance(node, list):
            return [resolve(value) for value in cast(list[Any], node)]
        return node

    return cast(dict[str, Any], resolve(schema))


MAX_STATEMENT_IDS = 60
STATEMENT_IDS = tuple(f"T{number}" for number in range(1, MAX_STATEMENT_IDS + 1))


def constrain_ids(schema: dict[str, Any], block_ids: Sequence[str]) -> dict[str, Any]:
    """The provider schema with ids limited to enums, so constrained decoding cannot produce an
    id that validation rejects: every citation's block_id to `block_ids` (never a statement id or
    an invented block), and statement ids and `covers` entries to T1..T60. Strict decoding drops
    `pattern`, so the enum is what enforces the format. Code still checks every id."""
    constrained = copy.deepcopy(schema)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            mapping = cast(dict[str, Any], node)
            properties: object = mapping.get("properties")
            if isinstance(properties, dict):
                fields = cast(dict[str, Any], properties)
                if {"block_id", "quote"} <= fields.keys():
                    fields["block_id"] = {**fields["block_id"], "enum": list(block_ids)}
                if {"id", "kind", "summary"} <= fields.keys():
                    fields["id"] = {**fields["id"], "enum": list(STATEMENT_IDS)}
                covers: object = fields.get("covers")
                if isinstance(covers, dict) and "items" in covers:
                    entries = cast(dict[str, Any], covers)
                    items = {**cast(dict[str, Any], entries["items"]), "enum": list(STATEMENT_IDS)}
                    fields["covers"] = {**entries, "items": items}
            for value in mapping.values():
                walk(value)
        elif isinstance(node, list):
            for value in cast(list[Any], node):
                walk(value)

    walk(constrained)
    return constrained
