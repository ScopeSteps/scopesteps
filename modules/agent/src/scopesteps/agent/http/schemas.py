from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from scopesteps.agent.application.schemas import DraftBacklog, DraftBacklogV3, DraftBacklogV4
from scopesteps.agent.client import MessageId, QuestionId, RunId
from scopesteps.agent.domain.conversation import MAX_MESSAGE_CHARS
from scopesteps.backlog.client import BacklogVersionId
from scopesteps.evidence.client import EvidenceRef
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceBlockId, SourceVersionId

RunMode = Literal["initial", "change"]
RunModeShown = Literal["initial", "change", "reply"]
RunStatus = Literal[
    "created",
    "running",
    "waiting_for_input",
    "ready_for_review",
    "failed",
    "cancelled",
    "completed",
]
MAX_REQUEST_TEXT_CHARS = 2000
# Bounds the lookups one request can ask for. The word limit on a project's current sources
# keeps any useful selection far smaller.
MAX_RUN_SOURCE_VERSIONS = 50


class CreateRunRequest(BaseModel):
    mode: RunMode = Field(
        description="initial drafts a backlog from source versions. change analyses a change "
        "request against the current baseline; it pins the baseline's sources and the request "
        "itself, so it takes no source_version_ids."
    )
    source_version_ids: list[SourceVersionId] = Field(
        default=[],
        max_length=MAX_RUN_SOURCE_VERSIONS,
        description="initial only: any of the project's source versions, each once, from "
        "sources it has not removed. Their paragraphs are numbered in this order.",
    )
    base_version_id: BacklogVersionId | None = Field(
        default=None, description="change only: the approved baseline the request is made on."
    )
    base_content_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        description="change only: that baseline's content hash, as the requester saw it.",
    )
    request_text: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_REQUEST_TEXT_CHARS,
        description="change only: what should change, stored as citable evidence.",
    )

    @model_validator(mode="after")
    def check_mode_fields(self) -> Self:
        change_fields = (self.base_version_id, self.base_content_hash, self.request_text)
        if self.mode == "change":
            if any(value is None for value in change_fields):
                raise ValueError(
                    "A change run requires base_version_id, base_content_hash and request_text"
                )
            if self.source_version_ids:
                raise ValueError("A change run pins its sources itself")
        else:
            if any(value is not None for value in change_fields):
                raise ValueError("An initial run takes no baseline or request text")
            if not self.source_version_ids:
                raise ValueError("An initial run needs at least one source version")
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
    mode: RunModeShown = Field(
        description="reply: the read-only work that answers one conversation message. change: "
        "the analysis of one change request against the baseline."
    )
    status: RunStatus = Field(
        description="completed: a reply run that answered its message, or a change run that "
        "found no change needed. A change run that proposes a change ends ready_for_review."
    )
    stage: Literal["explore", "draft", "reply", "change"] = Field(
        description="What the next step does: read the sources and ask, write the draft, "
        "reply to a message, or write the change set."
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
    draft: DraftBacklog | DraftBacklogV3 | DraftBacklogV4 | None = Field(
        description="The draft as the model wrote it, once an initial run is ready_for_review. "
        "Block ids it cites are resolved by block_refs. Review the saved candidate instead."
    )
    block_refs: list[BlockRef]
    problems: list[str] = Field(description="Check problems still on the draft after its repair.")
    candidate_version_id: BacklogVersionId | None = Field(
        description="The backlog version saved from this run once it is ready_for_review: a "
        "draft, or for a change run a candidate in review (see its change set)."
    )
    change_request_id: UUID | None = Field(description="The change request a change run analyses.")
    base_version_id: BacklogVersionId | None = Field(
        description="The baseline a change run analyses the request against."
    )
    error: RunError | None


class AnswerRequest(BaseModel):
    question_id: QuestionId
    answer: str | None = Field(default=None, min_length=1, max_length=MAX_REQUEST_TEXT_CHARS)
    skip: bool = False
    expected_revision: int | None = Field(
        default=None,
        description="The run revision the answer was given against; a stale one is 409. "
        "Required to change an earlier answer or skip.",
    )

    @model_validator(mode="after")
    def check_answer_or_skip(self) -> Self:
        if self.skip == (self.answer is not None):
            raise ValueError("Provide exactly one of answer or skip")
        return self


class MessageAuthor(BaseModel):
    user_id: UserId
    display_name: str = Field(description="The name when the message was written.")


class MessageCitation(BaseModel):
    """A quote that resolves to a source paragraph (`evidence`) or a recorded answer
    (`question_id`)."""

    quote: str
    evidence: EvidenceRef | None
    question_id: QuestionId | None


class MessageClaim(BaseModel):
    text: str
    basis: Literal["cited", "agent"] = Field(
        description="cited: backed by the citations. agent: the agent's own words, with no "
        "evidence; show it as such."
    )
    citations: list[MessageCitation]


class MessageQuestion(BaseModel):
    """The question's state now, which may have changed since the message was written."""

    id: QuestionId
    run_id: RunId
    round: int
    subject: str
    why_it_matters: str
    status: Literal["open", "answered", "skipped"]
    answer: str | None
    answered_by: UserId | None
    answered_at: datetime | None


MessageKind = Literal[
    "message",
    "change_request",
    "reply",
    "question",
    "answer",
    "skip",
    "answer_changed",
    "event",
    "analysis",
]
ConversationEvent = Literal[
    "run.started",
    "run.ready_for_review",
    "run.failed",
    "run.cancelled",
    "reply.failed",
    "reply.cancelled",
    "change.ready_for_review",
    "change.no_change_needed",
    "change.approved",
    "change.rejected",
]


class MessageResponse(BaseModel):
    id: MessageId
    role: Literal["user", "agent", "system"]
    kind: MessageKind
    text: str = Field(
        description="What was said. Empty for a skip; for a reply or an analysis, its claims "
        "joined by blank lines."
    )
    created_at: datetime
    author: MessageAuthor | None = Field(
        description="The person who wrote it, or whose action an event reports."
    )
    run_id: RunId | None
    question_id: QuestionId | None
    event: ConversationEvent | None = Field(description="Set exactly for kind event.")
    change_request_id: UUID | None = Field(
        description="For change.approved and change.rejected: the change request decided."
    )
    baseline_version: int | None = Field(
        description="For change.approved: the baseline number the candidate became. For "
        "change.rejected: the unchanged current baseline number."
    )
    claims: list[MessageClaim] = Field(description="Set for a reply and an analysis.")
    question: MessageQuestion | None = Field(
        description="For a question or an answer: that question's current state."
    )


class ActiveRun(BaseModel):
    id: RunId
    mode: RunModeShown
    status: RunStatus


class ConversationResponse(BaseModel):
    messages: list[MessageResponse] = Field(description="Newest first.")
    next_cursor: str | None = Field(
        description="Pass as cursor for older messages; null on the oldest page."
    )
    active_run: ActiveRun | None = Field(
        description="Agent work in progress, if any: created, running or waiting for answers. "
        "Advance it, answer it or stop it."
    )


class PostMessageRequest(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=MAX_MESSAGE_CHARS,
        description="The limit is also reported as limits.conversation.max_message_chars by "
        "GET /projects/{id}.",
    )
    kind: Literal["message", "change_request"] = Field(
        default="message",
        description="change_request asks to change the approved baseline; it needs "
        "base_version_id and base_content_hash.",
    )
    base_version_id: BacklogVersionId | None = Field(
        default=None, description="change_request only: the baseline the request is made on."
    )
    base_content_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        description="change_request only: that baseline's content hash, as the requester saw it.",
    )

    @model_validator(mode="after")
    def check_baseline_fields(self) -> Self:
        named = (self.base_version_id, self.base_content_hash)
        if self.kind == "change_request" and any(value is None for value in named):
            raise ValueError("A change request needs base_version_id and base_content_hash")
        if self.kind == "message" and any(value is not None for value in named):
            raise ValueError("A message names no baseline")
        return self


class PostMessageResponse(BaseModel):
    message: MessageResponse
    run: RunResponse = Field(
        description="The reply run, or for a change request the change run. Call "
        "POST /runs/{id}/advance until it ends."
    )
