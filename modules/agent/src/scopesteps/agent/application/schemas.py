"""Typed model outputs and tool arguments. The JSON schemas sent to providers come from here.

Output is untrusted: provider-side schema enforcement only guarantees JSON shape, so every
response is validated again with these models before anything is persisted.
"""

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
