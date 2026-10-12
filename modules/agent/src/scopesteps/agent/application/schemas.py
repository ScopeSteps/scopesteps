"""Typed model outputs and tool arguments. The JSON schemas sent to providers come from here.

Output is untrusted: provider-side schema enforcement only guarantees JSON shape, so every
response is validated again with these models before anything is persisted.
"""

from dataclasses import dataclass
from typing import Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

DRAFT_SCHEMA_VERSION = "draft-backlog.v1"
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


class Statement(_Output):
    kind: Literal["confirmed", "exclusion", "proposal", "conflict", "open_question"]
    summary: str = Field(min_length=1)
    citations: list[Citation] = Field(min_length=1)


class DraftCriterion(_Output):
    text: str = Field(min_length=1)
    origin: Literal["source", "proposed"] = Field(
        description="'source' only when the citations state it; otherwise 'proposed'."
    )
    citations: list[Citation]


class DraftItem(_Output):
    ref: str = Field(pattern=r"^(E|S)\d+$", description="E1, E2 for epics; S1..S8 for stories.")
    kind: Literal["epic", "story"]
    parent_ref: str | None = Field(description="Epic ref for a story; null for an epic.")
    title: str = Field(min_length=1, max_length=200)
    description: str
    criteria: list[DraftCriterion]
    assumptions: list[str]
    open_questions: list[str]


class DraftQuestion(_Output):
    subject: str = Field(min_length=1)
    question: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    citations: list[Citation]


class DraftBacklog(_Output):
    statements: list[Statement]
    items: list[DraftItem] = Field(max_length=MAX_EPICS + MAX_STORIES)
    questions: list[DraftQuestion] = Field(max_length=6)

    @model_validator(mode="after")
    def check_structure(self) -> Self:
        refs = [item.ref for item in self.items]
        if len(refs) != len(set(refs)):
            raise ValueError("Item refs must be unique")
        epics = {item.ref for item in self.items if item.kind == "epic"}
        if len(epics) > MAX_EPICS or len(self.items) - len(epics) > MAX_STORIES:
            raise ValueError(f"At most {MAX_EPICS} epics and {MAX_STORIES} stories")
        for item in self.items:
            if item.kind == "epic" and item.parent_ref is not None:
                raise ValueError(f"Epic {item.ref} cannot have a parent")
            if item.kind == "story" and item.parent_ref not in epics:
                raise ValueError(f"Story {item.ref} must belong to an epic")
            for criterion in item.criteria:
                if criterion.origin == "source" and not criterion.citations:
                    raise ValueError(f"{item.ref}: a sourced criterion needs a citation")
        return self


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
