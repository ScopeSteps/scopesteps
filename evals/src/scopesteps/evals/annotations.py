"""The answer key for one pack: what a correct run must include, exclude, ask about or ignore.

Annotations describe meaning, not story wording, so scoring never depends on exact phrasing.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1

# Proposed POC limits (POC Implementation Plan, section 2).
MAX_REVIEWER_TEXT_CHARS = 2000

SourceFile = Literal["brief.md", "transcript.md", "change_request.txt"]
INITIAL_SOURCE_FILES: tuple[SourceFile, ...] = ("brief.md", "transcript.md")

AnnotationKind = Literal[
    "confirmed_requirement",
    "exclusion",
    "proposal",
    "conflict",
    "missing_decision",
    "injection",
    "expected_change_impact",
]
Expectation = Literal[
    "include", "exclude", "not_commit", "ask", "ignore", "add", "modify", "remove", "unchanged"
]

ALLOWED_EXPECTATIONS: dict[AnnotationKind, frozenset[Expectation]] = {
    "confirmed_requirement": frozenset({"include"}),
    "exclusion": frozenset({"exclude"}),
    "proposal": frozenset({"not_commit"}),
    "conflict": frozenset({"ask"}),
    "missing_decision": frozenset({"ask"}),
    "injection": frozenset({"ignore"}),
    "expected_change_impact": frozenset({"ask", "add", "modify", "remove", "unchanged"}),
}
MIN_EVIDENCE: dict[AnnotationKind, int] = {
    "confirmed_requirement": 1,
    "exclusion": 1,
    "proposal": 1,
    "conflict": 2,
    "missing_decision": 0,
    "injection": 1,
    "expected_change_impact": 0,
}
EXPECTATIONS_NEEDING_TARGETS = frozenset({"modify", "remove", "unchanged"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Evidence(_Strict):
    file: SourceFile
    paragraph: int = Field(ge=1)
    quote: str = Field(min_length=1)


class Annotation(_Strict):
    id: str = Field(pattern=r"^[A-Z]{2}-\d{2}$")
    kind: AnnotationKind
    statement: str = Field(min_length=1)
    expect: Expectation
    evidence: list[Evidence] = []
    relates_to: list[str] = []

    @property
    def phase(self) -> Literal["initial", "change"]:
        return "change" if self.kind == "expected_change_impact" else "initial"

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        if self.expect not in ALLOWED_EXPECTATIONS[self.kind]:
            raise ValueError(f"{self.id}: kind {self.kind} cannot expect {self.expect}")
        if len(self.evidence) < MIN_EVIDENCE[self.kind]:
            raise ValueError(f"{self.id}: {self.kind} needs {MIN_EVIDENCE[self.kind]}+ evidence")
        if (
            self.phase == "change"
            and self.expect not in EXPECTATIONS_NEEDING_TARGETS
            and not self.evidence
        ):
            raise ValueError(f"{self.id}: a change impact to {self.expect} needs evidence")
        if self.expect in EXPECTATIONS_NEEDING_TARGETS and not self.relates_to:
            raise ValueError(f"{self.id}: expect {self.expect} needs relates_to")
        if self.phase == "initial" and any(e.file == "change_request.txt" for e in self.evidence):
            raise ValueError(f"{self.id}: only change impacts may cite change_request.txt")
        if self.id in self.relates_to:
            raise ValueError(f"{self.id}: cannot relate to itself")
        return self


class PackInfo(_Strict):
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class AnnotationFile(_Strict):
    schema_version: Literal[1]
    pack: PackInfo
    annotations: list[Annotation] = Field(min_length=1)

    @model_validator(mode="after")
    def check_references(self) -> Self:
        ids = [annotation.id for annotation in self.annotations]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"Duplicate annotation ids: {', '.join(duplicates)}")
        for annotation in self.annotations:
            unknown = sorted(set(annotation.relates_to) - set(ids))
            if unknown:
                raise ValueError(f"{annotation.id}: unknown relates_to {', '.join(unknown)}")
        return self

    def get(self, annotation_id: str) -> Annotation | None:
        return next((a for a in self.annotations if a.id == annotation_id), None)


class ReviewerAnswer(_Strict):
    """A scripted reviewer reply. `answer: null` means the reviewer skips the question."""

    question_for: str = Field(pattern=r"^[A-Z]{2}-\d{2}$")
    answered_by: str = Field(min_length=1)
    answer: str | None = Field(min_length=1, max_length=MAX_REVIEWER_TEXT_CHARS)


class AnswerFile(_Strict):
    schema_version: Literal[1]
    answers: list[ReviewerAnswer]
