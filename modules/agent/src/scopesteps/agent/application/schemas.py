"""Typed model outputs and tool arguments. The JSON schemas sent to providers come from here.

Output is untrusted: provider-side schema enforcement only guarantees JSON shape, so every
response is validated again with these models before anything is persisted.
"""

import copy
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Self, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from scopesteps.projects.client import (
    MAX_EVIDENCE,
    MAX_PEOPLE_PER_RUN,
    MAX_PERSON_NAME_CHARS,
    MAX_ROLE_CHARS,
    MAX_SAID_CHARS,
)

SchemaName = Literal[
    "draft-backlog.v1",
    "draft-backlog.v2",
    "draft-backlog.v3",
    "draft-backlog.v4",
    "draft-backlog.v5",
]
DRAFT_SCHEMA_VERSION: SchemaName = "draft-backlog.v2"
MAX_EPICS = 2
MAX_STORIES = 8


@dataclass(frozen=True)
class SpeakerNote:
    """Who speaks in a transcript paragraph, as people on the project confirmed it (ADR 0012).

    `label` is how the transcript writes the speaker. `name` and `meeting_role` are set only for
    a confirmed participant; `not_a_person` when an editor said the label is not a person.
    """

    label: str
    name: str | None = None
    meeting_role: str | None = None
    person_id: UUID | None = None
    not_a_person: bool = False

    @property
    def confirmed(self) -> bool:
        """An editor said who the speaker is, or that the label is not a person."""
        return self.not_a_person or self.name is not None

    def describe(self) -> str:
        """How a prompt shows it: "Dana: Dana Ruiz, Sponsor", "Sam: role unknown"."""
        if self.not_a_person:
            return f"{self.label}: not a person"
        if self.name is None:
            return f"{self.label}: role unknown"
        return f"{self.label}: {self.name}, {self.meeting_role or 'role unknown'}"


@dataclass(frozen=True)
class SourceBlockInput:
    """A citable passage shown to the model. `id` is what the model cites (B1, A1, ...).

    `speakers` is set for a transcript paragraph that holds speech.
    """

    id: str
    label: str
    text: str
    speakers: tuple[SpeakerNote, ...] = ()


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


def _check_statements(statements: Sequence[Statement], items: Sequence[DraftItem]) -> None:
    ids = [statement.id for statement in statements]
    if len(ids) != len(set(ids)):
        raise ValueError("Statement ids must be unique")
    for item in items:
        unknown = sorted(set(item.covers) - set(ids))
        if unknown:
            raise ValueError(f"{item.ref} covers unknown statements {', '.join(unknown)}")


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
        _check_statements(self.statements, self.items)
        return self


class DraftDecision(DraftQuestion):
    """draft-backlog.v3: a question names the stories that wait for its answer."""

    affects: list[str] = Field(
        description="Refs of the stories that cannot be approved until this is answered; empty "
        "when no story depends on it."
    )


class DraftBacklogV3(_Output):
    """draft-backlog.v3: draft-backlog.v2 with each question linked to the stories it blocks."""

    statements: list[Statement]
    items: list[DraftItem] = Field(max_length=MAX_EPICS + MAX_STORIES)
    questions: list[DraftDecision] = Field(max_length=6)

    @model_validator(mode="after")
    def check_structure(self) -> Self:
        _check_items(self.items)
        _check_statements(self.statements, self.items)
        stories = {item.ref for item in self.items if item.kind == "story"}
        for number, question in enumerate(self.questions, start=1):
            unknown = sorted(set(question.affects) - stories)
            if unknown:
                raise ValueError(
                    f"question {number} affects {', '.join(unknown)}, which are not stories here"
                )
        return self


# The people section is sent with every draft request, which must fit a small per-request token
# allowance on the backup provider (ADR 0006), so its schema carries almost no descriptions (the
# prompt explains the fields) and its citations drop the ones `Citation` repeats.
class PersonCitation(Citation):
    block_id: str
    quote: str = Field(min_length=1)


# The size limits below are sent to the provider but not enforced by validation: people are
# secondary to the backlog, so an over-long entry must not invalidate a whole draft.
# `candidate.to_people` trims to the same limits before anything is stored.
class DraftPerson(_Output):
    """A person the sources name."""

    ref: str = Field(pattern=r"^P\d+$")
    name: str = Field(min_length=1, json_schema_extra={"maxLength": MAX_PERSON_NAME_CHARS})
    role: str = Field(
        description="Empty when no source states one.",
        json_schema_extra={"maxLength": MAX_ROLE_CHARS},
    )
    said: str = Field(
        description="One short sentence in your words; may be empty.",
        json_schema_extra={"maxLength": MAX_SAID_CHARS},
    )
    citations: list[PersonCitation] = Field(json_schema_extra={"maxItems": MAX_EVIDENCE})
    rights: Literal["decides", "advises", "not_stated"] = Field(
        description="Only what a source states."
    )
    rights_citations: list[PersonCitation] = Field(
        description="Empty when rights is not_stated.",
        json_schema_extra={"maxItems": MAX_EVIDENCE},
    )


def _check_people(people: Sequence[DraftPerson]) -> None:
    refs = [person.ref for person in people]
    if len(refs) != len(set(refs)):
        raise ValueError("Person refs must be unique")


class DraftBacklogV4(DraftBacklogV3):
    """draft-backlog.v4: draft-backlog.v3 plus the people the sources name."""

    people: list[DraftPerson] = Field(json_schema_extra={"maxItems": MAX_PEOPLE_PER_RUN})

    @model_validator(mode="after")
    def check_people(self) -> Self:
        _check_people(self.people)
        return self


class DraftPersonV5(DraftPerson):
    """A person the sources name; a transcript speaker an editor confirmed is named by id."""

    speaker: str = Field(description="Participant id, or empty.")


class DraftBacklogV5(DraftBacklogV4):
    """draft-backlog.v5: draft-backlog.v4 with people who may be participants named by id, whose
    identity and paragraphs code takes from the editors' confirmation instead of a quote."""

    people: list[DraftPersonV5] = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        json_schema_extra={"maxItems": MAX_PEOPLE_PER_RUN}
    )


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


class PatchDecision(DraftDecision):
    replaces: int | None = Field(
        description="Number of the question this replaces (1 is the first), or null to add one."
    )


class DraftPatchV3(_Output):
    """Targeted repair output for draft-backlog.v3."""

    statements: list[Statement] = Field(
        description="New statements, or existing ones rewritten in full under the same id."
    )
    items: list[DraftItem] = Field(
        description="New items, or existing ones rewritten in full under the same ref."
    )
    questions: list[PatchDecision]


class DraftPatchV4(DraftPatchV3):
    """Targeted repair output for draft-backlog.v4."""

    people: list[DraftPerson] = Field(
        description="New people, or existing ones rewritten in full under the same ref."
    )


class DraftPatchV5(DraftPatchV4):
    """Targeted repair output for draft-backlog.v5."""

    people: list[DraftPersonV5] = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        description="New people, or existing ones rewritten in full under the same ref."
    )


def apply_patch(
    draft: DraftBacklog | DraftBacklogV3, patch: DraftPatch | DraftPatchV3
) -> DraftBacklog | DraftBacklogV3:
    """Replace statements, items and people by id or ref, add new ones, then validate the whole
    draft."""
    statements = {statement.id: statement for statement in draft.statements}
    statements |= {statement.id: statement for statement in patch.statements}
    items = {item.ref: item for item in draft.items}
    items |= {item.ref: item for item in patch.items}
    questions = [question.model_dump() for question in draft.questions]
    for patched in patch.questions:
        question = patched.model_dump(exclude={"replaces"})
        if patched.replaces is not None and 1 <= patched.replaces <= len(questions):
            questions[patched.replaces - 1] = question
        else:
            questions.append(question)
    merged: dict[str, Any] = {
        "statements": [statement.model_dump() for statement in statements.values()],
        "items": [item.model_dump() for item in items.values()],
        "questions": questions,
    }
    if isinstance(draft, DraftBacklogV4):
        people = {person.ref: person for person in draft.people}
        if isinstance(patch, DraftPatchV4):
            people |= {person.ref: person for person in patch.people}
        merged["people"] = [person.model_dump() for person in people.values()]
    return type(draft).model_validate(merged)


AnyDraft = DraftBacklogV5 | DraftBacklogV4 | DraftBacklogV3 | DraftBacklog | DraftBacklogV1
DRAFT_SCHEMAS: dict[SchemaName, type[AnyDraft]] = {
    "draft-backlog.v1": DraftBacklogV1,
    "draft-backlog.v2": DraftBacklog,
    "draft-backlog.v3": DraftBacklogV3,
    "draft-backlog.v4": DraftBacklogV4,
    "draft-backlog.v5": DraftBacklogV5,
}
PATCH_SCHEMAS: dict[type[AnyDraft], type[DraftPatch] | type[DraftPatchV3]] = {
    DraftBacklog: DraftPatch,
    DraftBacklogV3: DraftPatchV3,
    DraftBacklogV4: DraftPatchV4,
    DraftBacklogV5: DraftPatchV5,
}
"""The targeted-repair output of each schema that has one."""


def parse_draft(data: object) -> AnyDraft:
    """Load a stored draft of any schema version. A draft-backlog.v3 draft without questions has
    the same shape as a draft-backlog.v2 one and loads as that."""
    for schema in (DraftBacklog, DraftBacklogV3, DraftBacklogV4, DraftBacklogV5):
        try:
            return schema.model_validate(data)
        except ValidationError:
            continue
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


class GetStoryArgs(_Output):
    """Arguments of the read-only `get_story` tool a reply may call."""

    item_id: str = Field(
        description="The item's label in the backlog, exactly as given, e.g. 'S2'."
    )


class ListOpenDecisionsArgs(_Output):
    """`list_open_decisions` takes no arguments."""


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
PERSON_REFS = tuple(f"P{number}" for number in range(1, MAX_PEOPLE_PER_RUN + 1))


def constrain_ids(
    schema: dict[str, Any], block_ids: Sequence[str], speaker_ids: Sequence[str] = ()
) -> dict[str, Any]:
    """The provider schema with ids limited to enums, so constrained decoding cannot produce an
    id that validation rejects: every citation's block_id to `block_ids` (never a statement id or
    an invented block), statement ids and `covers` entries to T1..T60, and person refs to
    P1..P10, and a person's `speaker` to the request's participant ids or empty. Strict decoding
    drops `pattern`, so the enum is what enforces the format. Code still checks every id."""
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
                if {"ref", "name", "rights"} <= fields.keys():
                    fields["ref"] = {**fields["ref"], "enum": list(PERSON_REFS)}
                    if "speaker" in fields:
                        fields["speaker"] = {**fields["speaker"], "enum": ["", *speaker_ids]}
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
