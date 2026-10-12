from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from scopesteps.agent.client import QuestionId, RunId
from scopesteps.backlog.client import BacklogVersionId
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceBlockId, SourceVersionId

RunMode = Literal["initial", "change"]
RunStatus = Literal[
    "created", "running", "waiting_for_input", "ready_for_review", "failed", "cancelled"
]
MAX_REQUEST_TEXT_CHARS = 2000


class CreateRunRequest(BaseModel):
    mode: RunMode
    source_version_ids: list[SourceVersionId] = Field(min_length=1)
    base_version_id: BacklogVersionId | None = None
    request_text: str | None = Field(default=None, min_length=1, max_length=MAX_REQUEST_TEXT_CHARS)

    @model_validator(mode="after")
    def check_mode_fields(self) -> Self:
        if self.mode == "change" and (self.base_version_id is None or self.request_text is None):
            raise ValueError("A change run requires base_version_id and request_text")
        if self.mode == "initial" and self.base_version_id is not None:
            raise ValueError("An initial run cannot have a base_version_id")
        return self


class RunUsage(BaseModel):
    model_turns: int
    tool_calls: int
    clarification_rounds: int


class ClarificationQuestion(BaseModel):
    id: QuestionId
    subject: str
    text: str
    why_it_matters: str
    evidence_block_ids: list[SourceBlockId]
    status: Literal["open", "answered", "skipped"]


class RunError(BaseModel):
    code: str
    message: str
    retryable: bool


class RunResponse(BaseModel):
    id: RunId
    project_id: ProjectId
    mode: RunMode
    status: RunStatus
    revision: int
    usage: RunUsage
    questions: list[ClarificationQuestion]
    candidate_version_id: BacklogVersionId | None
    error: RunError | None


class AnswerRequest(BaseModel):
    question_id: QuestionId
    answer: str | None = Field(default=None, min_length=1, max_length=MAX_REQUEST_TEXT_CHARS)
    skip: bool = False

    @model_validator(mode="after")
    def check_answer_or_skip(self) -> Self:
        if self.skip == (self.answer is not None):
            raise ValueError("Provide exactly one of answer or skip")
        return self
