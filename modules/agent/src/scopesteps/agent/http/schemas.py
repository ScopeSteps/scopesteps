from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from scopesteps.agent.application.schemas import DraftBacklog, DraftBacklogV3
from scopesteps.agent.client import QuestionId, RunId
from scopesteps.backlog.client import BacklogVersionId
from scopesteps.evidence.client import EvidenceRef
from scopesteps.identity.client import UserId
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
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    total_tokens: int
    cost_usd_estimate: str = Field(description="Estimated cost at paid rates, as a decimal string.")


class RunLimitsResponse(BaseModel):
    """The limits pinned when the run was created."""

    max_turns: int
    max_tool_calls: int
    max_clarification_rounds: int
    max_total_tokens: int
    max_cost_usd: str | None


class ProjectUsage(BaseModel):
    cost_usd_estimate: str = Field(description="Estimated cost of every run in the project.")
    cost_limit_usd: str | None


class ClarificationQuestion(BaseModel):
    id: QuestionId
    subject: str
    text: str
    why_it_matters: str
    evidence_block_ids: list[SourceBlockId]
    evidence: list[EvidenceRef] = Field(
        description="The pinned paragraphs the question is about, each with its source version."
    )
    status: Literal["open", "answered", "skipped"]
    round: int
    answer: str | None
    answered_by: UserId | None = Field(description="Who answered or skipped the question.")
    answered_at: datetime | None


class RunError(BaseModel):
    code: str
    message: str
    retryable: bool


class BlockRef(BaseModel):
    """What a block label cited in the draft refers to: a source paragraph or a reviewer answer."""

    label: str = Field(description="The id the draft cites, e.g. B12 or A1.")
    source_block_id: SourceBlockId | None
    question_id: QuestionId | None


class RunResponse(BaseModel):
    id: RunId
    project_id: ProjectId
    mode: RunMode
    status: RunStatus
    stage: Literal["explore", "draft"] = Field(
        description="What the next step does: read the sources and ask, or write the draft."
    )
    revision: int
    source_version_ids: list[SourceVersionId] = Field(
        description="The source versions pinned when the run was created."
    )
    provider: str
    model_id: str
    fallback_reason: str | None = Field(
        description="Set when the run uses the backup provider, with why (ADR 0006)."
    )
    prompt_version: str
    usage: RunUsage
    limits: RunLimitsResponse
    project_usage: ProjectUsage
    questions: list[ClarificationQuestion]
    draft: DraftBacklog | DraftBacklogV3 | None = Field(
        description="The draft as the model wrote it, once the run is ready_for_review. Block "
        "ids it cites are resolved by block_refs. Review the saved candidate instead."
    )
    block_refs: list[BlockRef]
    problems: list[str] = Field(description="Check problems still on the draft after its repair.")
    candidate_version_id: BacklogVersionId | None = Field(
        description="The draft backlog version saved from this run, once it is ready_for_review."
    )
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
