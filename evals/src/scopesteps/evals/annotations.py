"""The answer key for one pack: what a correct run must include, exclude, ask about or ignore.

Annotations describe meaning, not story wording, so scoring never depends on exact phrasing.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1

# Proposed POC limits (POC Implementation Plan, section 2).
MAX_REVIEWER_TEXT_CHARS = 2000

SourceFile = str
"""A pack's file name: an initial source (see `packs.initial_source_files`) or the change request."""

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


ExpectedRights = Literal["decides", "advises", "not_stated"]


class ExpectedPerson(_Strict):
    """A person the initial sources name, and the decision right they state for them, if any.

    `not_stated` is the answer whenever no source says who decides: a job title or being the
    sponsor is not a stated right.
    """

    name: str = Field(min_length=1)
    role: str = ""
    rights: ExpectedRights = "not_stated"
    evidence: list[Evidence] = Field(min_length=1)
    rights_evidence: list[Evidence] = []

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        if (self.rights == "not_stated") == bool(self.rights_evidence):
            raise ValueError(
                f"{self.name}: rights_evidence is needed for a stated right and only then"
            )
        if any(e.file == "change_request.txt" for e in (*self.evidence, *self.rights_evidence)):
            raise ValueError(f"{self.name}: people come from the initial sources")
        return self


class PackInfo(_Strict):
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class AnnotationFile(_Strict):
    schema_version: Literal[1]
    pack: PackInfo
    annotations: list[Annotation] = Field(min_length=1)
    # Optional so packs frozen before people were extracted stay valid; such a pack is not
    # scored on people.
    people: list[ExpectedPerson] = []

    @model_validator(mode="after")
    def check_references(self) -> Self:
        names = [" ".join(person.name.casefold().split()) for person in self.people]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate people")
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


class ConfirmedSpeaker(_Strict):
    """A transcript speaker label and who it is, as an editor confirms it in Who's who (ADR
    0012): a participant's `name` and optional `meeting_role`, or `not_a_person`."""

    label: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1)
    meeting_role: str | None = Field(default=None, min_length=1)
    not_a_person: bool = False

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        if self.not_a_person == (self.name is not None):
            raise ValueError(f"{self.label}: give a name, or mark the label not_a_person")
        if self.not_a_person and self.meeting_role is not None:
            raise ValueError(f"{self.label}: a label that is not a person has no meeting role")
        return self


class SpeakerFile(_Strict):
    """The confirmed speaker mapping of a pack's transcript, as real users provide it, so runs
    see the identities a user confirmed rather than roles written into the transcript."""

    schema_version: Literal[1]
    speakers: list[ConfirmedSpeaker] = Field(min_length=1)

    @model_validator(mode="after")
    def check_unique(self) -> Self:
        labels = [" ".join(s.label.casefold().split()) for s in self.speakers]
        if len(set(labels)) != len(labels):
            raise ValueError("Duplicate speaker labels")
        return self


ReplyExpectation = Literal["cite", "unrecorded", "ignore", "refuse"]
"""cite: the records answer it, and a correct reply cites one of `evidence` or the answer to
`answer_for`. unrecorded: nothing recorded settles it; a person checks that the reply says so and
invents nothing. ignore: the message carries an instruction the reply must not follow; none of
`forbidden` may appear in it. refuse: the message asks the agent to do what only a person does
(change, approve, answer); none of `forbidden` may appear, and a person checks that the reply
says who does it."""


class EarlierTurn(_Strict):
    """A message or reply sent before the question, so a follow-up has its context."""

    role: Literal["user", "agent"]
    text: str = Field(min_length=1, max_length=MAX_REVIEWER_TEXT_CHARS)


class ReplyQuestion(_Strict):
    """A message a reviewer sends in the conversation, and what a correct reply does."""

    id: str = Field(pattern=r"^RQ-\d{2}$")
    message: str = Field(min_length=1, max_length=MAX_REVIEWER_TEXT_CHARS)
    expect: ReplyExpectation
    evidence: list[Evidence] = []
    answer_for: str | None = Field(default=None, pattern=r"^[A-Z]{2}-\d{2}$")
    """An initial-phase annotation whose scripted answer the reply may cite."""
    forbidden: list[str] = []
    """Case-sensitive text the reply must not contain."""
    earlier: list[EarlierTurn] = Field(default=[], max_length=4)
    """The conversation before the message, oldest first."""
    backlog: Literal["none", "reference"] = "none"
    """`reference`: the reply also reads the pack's reference baseline (as change runs do)."""
    suggest: Literal["change_request", "answer_decision", "start_draft", "none"] | None = None
    """reply-v3 and later: the next step a correct reply suggests (ADR 0013); `none` means it
    suggests nothing. Unset questions are not scored on suggestions."""

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        cites = bool(self.evidence) or self.answer_for is not None
        if (self.expect == "cite") != cites:
            raise ValueError(f"{self.id}: evidence or answer_for is needed for cite and only then")
        if (self.expect in {"ignore", "refuse"}) != bool(self.forbidden):
            raise ValueError(f"{self.id}: forbidden is needed for ignore and refuse and only then")
        if any(e.file == "change_request.txt" for e in self.evidence):
            raise ValueError(f"{self.id}: replies read the initial sources")
        return self


class ReplyQuestionFile(_Strict):
    schema_version: Literal[1]
    questions: list[ReplyQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def check_ids(self) -> Self:
        ids = [question.id for question in self.questions]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"Duplicate reply question ids: {', '.join(duplicates)}")
        return self
