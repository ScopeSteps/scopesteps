from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, and_, func, or_, select, update
from sqlalchemy.orm import Session

from scopesteps.agent.application.ports import Baseline, MessageCursor, Passage, Receipt
from scopesteps.agent.application.schemas import SpeakerNote
from scopesteps.agent.domain.budget import RunCounters, RunLimits
from scopesteps.agent.domain.conversation import CitedPassage, Claim, Message
from scopesteps.agent.domain.ids import MessageId, QuestionId, RunId, StepId
from scopesteps.agent.domain.model import ModelTurn, ToolResult, ToolResults, Turn, UserMessage
from scopesteps.agent.domain.run import (
    IN_PROGRESS,
    ChangeInputs,
    Lease,
    Question,
    QuestionStatus,
    Run,
    RunError,
    RunInputs,
    RunMode,
    RunStatus,
    RunStep,
    StepKind,
    TokenTotals,
)
from scopesteps.agent.domain.suggestion import (
    ProposedSuggestion,
    Suggestion,
    SuggestionKind,
    SuggestionStatus,
)
from scopesteps.agent.infrastructure.orm import (
    ConversationTurnRecord,
    MessageRecord,
    QuestionRecord,
    RequestReceiptRecord,
    RunRecord,
    RunStepRecord,
    SuggestionRecord,
)
from scopesteps.backlog.client import (
    BacklogOutline,
    BacklogVersion,
    BacklogVersionId,
    CandidateProposal,
    ChangeProposal,
    SavedChange,
    candidate_problems,
    change_candidate_problems,
    change_run_answer,
    current_backlog,
    load_scope_statuses,
    load_version,
    save_candidate,
    save_change_candidate,
)
from scopesteps.change_control.client import (
    ChangeAnalysis,
    ChangeRequestRef,
    ChangeSummary,
    OpenChangeRequest,
    open_change_request,
    record_change_analysis,
    record_change_failure,
)
from scopesteps.identity.client import UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId, SpeakerIdentity, SpeakerIdentityReader
from scopesteps.sources.client import (
    SourceBlockId,
    SourceVersionId,
    current_version_ids,
    load_passages,
    load_speaker_turns,
    record_change_request,
    removed_versions,
)


class SqlPassageReader:
    """Pinned paragraphs. With `identities`, transcript paragraphs also say who speaks in them:
    turns found by `sources`' parser, identities as people on the project confirmed them."""

    def __init__(self, session: Session, identities: SpeakerIdentityReader | None = None) -> None:
        self._session = session
        self._identities = identities

    def load(self, project_id: ProjectId, version_ids: Sequence[UUID]) -> list[Passage]:
        versions = [SourceVersionId(v) for v in version_ids]
        speakers = self._speakers(project_id, versions)
        return [
            Passage(
                block_id=passage.block_id,
                source_version_id=passage.source_version_id,
                source_kind=passage.source_kind,
                ordinal=passage.ordinal,
                text=passage.text,
                speakers=speakers.get(passage.block_id, ()),
            )
            for passage in load_passages(self._session, project_id, versions)
        ]

    def _speakers(
        self, project_id: ProjectId, versions: Sequence[SourceVersionId]
    ) -> dict[SourceBlockId, tuple[SpeakerNote, ...]]:
        if self._identities is None:
            return {}
        found: dict[SourceBlockId, tuple[SpeakerNote, ...]] = {}
        for turns in load_speaker_turns(self._session, project_id, versions):
            identities = self._identities(project_id, turns.source_id, list(turns.labels))
            for block_id, keys in turns.by_block.items():
                found[block_id] = tuple(
                    _note(turns.labels.get(key, key), identities.get(key)) for key in keys
                )
        return found

    def removed(self, project_id: ProjectId, version_ids: Sequence[UUID]) -> set[UUID]:
        return set(
            removed_versions(self._session, project_id, [SourceVersionId(v) for v in version_ids])
        )


def _note(label: str, identity: SpeakerIdentity | None) -> SpeakerNote:
    if identity is None or identity.status == "unconfirmed":
        return SpeakerNote(label)
    if identity.status == "not_a_person":
        return SpeakerNote(label, not_a_person=True)
    return SpeakerNote(label, identity.name, identity.meeting_role, identity.person_id)


class SqlCandidateStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def problems(self, proposal: CandidateProposal) -> list[str]:
        return candidate_problems(self._session, proposal)

    def save(self, proposal: CandidateProposal, now: datetime) -> None:
        save_candidate(self._session, proposal, now)


class SqlProjectContext:
    def __init__(self, session: Session) -> None:
        self._session = session

    def current_source_versions(self, project_id: ProjectId) -> list[SourceVersionId]:
        return current_version_ids(self._session, project_id)

    def backlog(self, project_id: ProjectId) -> BacklogOutline | None:
        return current_backlog(self._session, project_id)

    def has_baseline(self, project_id: ProjectId) -> bool:
        status = load_scope_statuses(self._session, [project_id])[project_id]
        return status.baseline_version_id is not None

    def baseline(self, project_id: ProjectId) -> Baseline | None:
        status = load_scope_statuses(self._session, [project_id])[project_id]
        if status.baseline_version_id is None or status.baseline_version is None:
            return None
        version = load_version(self._session, status.baseline_version_id)
        return None if version is None else Baseline(version, status.baseline_version)

    def version(self, version_id: UUID) -> BacklogVersion | None:
        return load_version(self._session, BacklogVersionId(version_id))


class SqlChangeStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def problems(self, proposal: ChangeProposal) -> list[str]:
        return change_candidate_problems(self._session, proposal)

    def save(self, proposal: ChangeProposal, now: datetime) -> SavedChange:
        return save_change_candidate(self._session, proposal, now)


class SqlChangeRequests:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record_text(
        self, project_id: ProjectId, text: str, recorded_by: UserId, now: datetime
    ) -> SourceVersionId:
        return record_change_request(self._session, project_id, text, recorded_by, now)

    def open(self, command: OpenChangeRequest, now: datetime) -> ChangeRequestRef:
        return open_change_request(self._session, command, now)

    def analyzed(
        self, run_id: RunId, analysis: ChangeAnalysis, now: datetime
    ) -> ChangeSummary | None:
        return record_change_analysis(self._session, run_id, analysis, now)

    def failed(self, run_id: RunId, code: str, now: datetime) -> None:
        record_change_failure(self._session, run_id, code, now)


class SqlDraftAnswers:
    def __init__(self, session: Session) -> None:
        self._session = session

    def change_answer(
        self, run_id: RunId, question_id: UUID, answer: str, decided_by: UserId, now: datetime
    ) -> UUID | None:
        return change_run_answer(
            self._session, run_id, question_id, answer, decided_by=decided_by, now=now
        )


class SqlRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_messages(self, messages: Sequence[Message]) -> None:
        self._session.add_all(
            MessageRecord(
                id=m.id,
                project_id=m.project_id,
                role=m.role,
                kind=m.kind,
                text=m.text,
                author_id=m.author_id,
                author_name=m.author_name,
                run_id=m.run_id,
                question_id=m.question_id,
                event=m.event,
                claims=[_claim_json(claim) for claim in m.claims],
                change_request_id=m.change_request_id,
                baseline_version=m.baseline_version,
                created_at=m.created_at,
            )
            for m in messages
        )
        self._session.flush()

    def newest_messages(
        self, project_id: ProjectId, *, before: MessageCursor | None, limit: int
    ) -> list[Message]:
        query = select(MessageRecord).where(MessageRecord.project_id == project_id)
        if before is not None:
            query = query.where(
                or_(
                    MessageRecord.created_at < before.created_at,
                    and_(
                        MessageRecord.created_at == before.created_at,
                        MessageRecord.id < before.id,
                    ),
                )
            )
        records = self._session.scalars(
            query.order_by(MessageRecord.created_at.desc(), MessageRecord.id.desc()).limit(limit)
        )
        return [_to_message(record) for record in records]

    def add_suggestion(self, suggestion: Suggestion) -> None:
        proposed = suggestion.proposed
        self._session.add(
            SuggestionRecord(
                message_id=suggestion.message_id,
                project_id=suggestion.project_id,
                kind=proposed.kind,
                status=suggestion.status,
                revision=suggestion.revision,
                request_text=proposed.request_text,
                version_id=proposed.version_id,
                decision_id=proposed.decision_id,
                decision_subject=proposed.decision_subject,
                answer=proposed.answer,
                created_at=suggestion.created_at,
                decided_by=suggestion.decided_by,
                decided_at=suggestion.decided_at,
            )
        )

    def suggestions_for(self, message_ids: Sequence[MessageId]) -> dict[MessageId, Suggestion]:
        if not message_ids:
            return {}
        records = self._session.scalars(
            select(SuggestionRecord)
            .where(SuggestionRecord.message_id.in_(list(message_ids)))
            .execution_options(populate_existing=True)
        )
        return {MessageId(record.message_id): _to_suggestion(record) for record in records}

    def save_suggestion(self, suggestion: Suggestion, *, expected_revision: int) -> bool:
        result = self._session.execute(
            update(SuggestionRecord)
            .where(
                SuggestionRecord.message_id == suggestion.message_id,
                SuggestionRecord.revision == expected_revision,
            )
            .values(
                status=suggestion.status,
                revision=suggestion.revision,
                decided_by=suggestion.decided_by,
                decided_at=suggestion.decided_at,
            )
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1

    def run_messages(self, run_id: RunId) -> list[Message]:
        records = self._session.scalars(
            select(MessageRecord)
            .where(MessageRecord.run_id == run_id)
            .order_by(MessageRecord.created_at, MessageRecord.id)
        )
        return [_to_message(record) for record in records]

    def claim_turn(self, project_id: ProjectId) -> bool:
        turn = self._session.get(ConversationTurnRecord, project_id, populate_existing=True)
        if turn is None:
            # A concurrent first turn fails this insert's primary key; that request then ends as
            # a retryable conflict, like any other lost race.
            self._session.add(ConversationTurnRecord(project_id=project_id, revision=1))
            self._session.flush()
            return True
        result = self._session.execute(
            update(ConversationTurnRecord)
            .where(
                ConversationTurnRecord.project_id == project_id,
                ConversationTurnRecord.revision == turn.revision,
            )
            .values(revision=turn.revision + 1)
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1

    def active_run(self, project_id: ProjectId) -> Run | None:
        record = self._session.scalars(
            select(RunRecord)
            .where(RunRecord.project_id == project_id, RunRecord.status.in_(IN_PROGRESS))
            .order_by(RunRecord.created_at.desc(), RunRecord.id.desc())
            .limit(1)
        ).one_or_none()
        return None if record is None else _to_run(record)

    def answered_questions(self, project_id: ProjectId) -> list[Question]:
        records = self._session.scalars(
            select(QuestionRecord)
            .join(RunRecord, RunRecord.id == QuestionRecord.run_id)
            .where(
                RunRecord.project_id == project_id,
                QuestionRecord.status == QuestionStatus.ANSWERED,
            )
            .order_by(QuestionRecord.answered_at, QuestionRecord.id)
        )
        return [_to_question(record) for record in records]

    def questions_by_id(self, ids: Sequence[UUID]) -> list[Question]:
        if not ids:
            return []
        records = self._session.scalars(select(QuestionRecord).where(QuestionRecord.id.in_(ids)))
        return [_to_question(record) for record in records]

    def get_run(self, run_id: RunId) -> Run | None:
        record = self._session.get(RunRecord, run_id, populate_existing=True)
        return None if record is None else _to_run(record)

    def add_run(self, run: Run) -> None:
        self._session.add(RunRecord(id=run.id, **_run_fields(run)))
        self._session.flush()

    def save_run(self, run: Run, *, expected_revision: int) -> bool:
        result = self._session.execute(
            update(RunRecord)
            .where(RunRecord.id == run.id, RunRecord.revision == expected_revision)
            .values(**_run_fields(run))
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1

    def add_usage(self, run: Run, *, since: Run) -> None:
        self._session.execute(
            update(RunRecord)
            .where(RunRecord.id == run.id)
            .values(
                model_turns=RunRecord.model_turns
                + (run.counters.model_turns - since.counters.model_turns),
                tool_calls=RunRecord.tool_calls
                + (run.counters.tool_calls - since.counters.tool_calls),
                total_tokens=RunRecord.total_tokens
                + (run.counters.total_tokens - since.counters.total_tokens),
                input_tokens=RunRecord.input_tokens
                + (run.totals.input_tokens - since.totals.input_tokens),
                output_tokens=RunRecord.output_tokens
                + (run.totals.output_tokens - since.totals.output_tokens),
                thinking_tokens=RunRecord.thinking_tokens
                + (run.totals.thinking_tokens - since.totals.thinking_tokens),
                cost_microusd=RunRecord.cost_microusd
                + (run.totals.cost_microusd - since.totals.cost_microusd),
            )
            .execution_options(synchronize_session=False)
        )

    def add_steps(self, steps: Sequence[RunStep]) -> None:
        if not steps:
            return
        last = self._session.scalar(
            select(func.max(RunStepRecord.sequence)).where(RunStepRecord.run_id == steps[0].run_id)
        )
        start = (last or 0) + 1
        self._session.add_all(
            RunStepRecord(
                id=step.id,
                run_id=step.run_id,
                sequence=start + offset,
                kind=step.kind,
                name=step.name,
                stage=step.stage,
                provider=step.provider,
                model_id=step.model_id,
                prompt_version=step.prompt_version,
                schema_version=step.schema_version,
                attempt=step.attempt,
                repair=step.repair,
                input_tokens=step.input_tokens,
                output_tokens=step.output_tokens,
                thinking_tokens=step.thinking_tokens,
                latency_ms=step.latency_ms,
                finish_reason=step.finish_reason,
                tool_calls=step.tool_calls,
                error_kind=step.error_kind,
                cost_microusd=step.cost_microusd,
                detail=dict(step.detail),
                created_at=step.created_at,
            )
            for offset, step in enumerate(steps)
        )
        self._session.flush()

    def steps(self, run_id: RunId) -> list[RunStep]:
        records = self._session.scalars(
            select(RunStepRecord)
            .where(RunStepRecord.run_id == run_id)
            .order_by(RunStepRecord.sequence)
        )
        return [
            RunStep(
                id=StepId(record.id),
                run_id=RunId(record.run_id),
                kind=_step_kind(record.kind),
                name=record.name,
                stage=record.stage,
                created_at=record.created_at,
                provider=record.provider,
                model_id=record.model_id,
                prompt_version=record.prompt_version,
                schema_version=record.schema_version,
                attempt=record.attempt,
                repair=record.repair,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                thinking_tokens=record.thinking_tokens,
                latency_ms=record.latency_ms,
                finish_reason=record.finish_reason,
                tool_calls=record.tool_calls,
                error_kind=record.error_kind,
                cost_microusd=record.cost_microusd,
                detail=record.detail,
                sequence=record.sequence,
            )
            for record in records
        ]

    def questions(self, run_id: RunId) -> list[Question]:
        records = self._session.scalars(
            select(QuestionRecord)
            .where(QuestionRecord.run_id == run_id)
            .order_by(QuestionRecord.round, QuestionRecord.id)
        )
        return [_to_question(record) for record in records]

    def save_questions(self, questions: Sequence[Question]) -> None:
        for question in questions:
            self._session.merge(
                QuestionRecord(
                    id=question.id,
                    run_id=question.run_id,
                    round=question.round,
                    call_id=question.call_id,
                    subject=question.subject,
                    text=question.text,
                    why_it_matters=question.why_it_matters,
                    block_labels=list(question.block_labels),
                    status=question.status,
                    answer=question.answer,
                    answer_label=question.answer_label,
                    answered_by=question.answered_by,
                    answered_at=question.answered_at,
                )
            )
        self._session.flush()

    def runs_pinning(self, project_id: ProjectId, version_ids: Collection[UUID]) -> list[RunId]:
        """Reply runs are left out: they only read, and the passages their replies cite stay
        readable after a source is removed (ADR 0009, ADR 0010)."""
        wanted = {str(version_id) for version_id in version_ids}
        rows = self._session.execute(
            select(RunRecord.id, RunRecord.inputs).where(
                RunRecord.project_id == project_id, RunRecord.mode != "reply"
            )
        )
        return [
            RunId(run_id)
            for run_id, inputs in rows
            if wanted.intersection(inputs["source_version_ids"])
        ]

    def open_question_counts(self, project_ids: Collection[ProjectId]) -> dict[ProjectId, int]:
        """One grouped query; projects with no open question are absent."""
        rows = self._session.execute(
            select(RunRecord.project_id, func.count(QuestionRecord.id))
            .join(QuestionRecord, QuestionRecord.run_id == RunRecord.id)
            .where(
                RunRecord.project_id.in_(list(project_ids)),
                RunRecord.status == RunStatus.WAITING_FOR_INPUT,
                QuestionRecord.status == QuestionStatus.OPEN,
            )
            .group_by(RunRecord.project_id)
        )
        return {ProjectId(project_id): count for project_id, count in rows}

    def project_cost_microusd(self, project_id: ProjectId) -> int:
        total = self._session.scalar(
            select(func.sum(RunRecord.cost_microusd)).where(RunRecord.project_id == project_id)
        )
        return int(total or 0)

    def find_receipt(self, actor_id: UserId, idempotency_key: str) -> Receipt | None:
        record = self._session.scalars(
            select(RequestReceiptRecord).where(
                RequestReceiptRecord.actor_id == actor_id,
                RequestReceiptRecord.idempotency_key == idempotency_key,
            )
        ).one_or_none()
        if record is None:
            return None
        return Receipt(
            actor_id=UserId(record.actor_id),
            idempotency_key=record.idempotency_key,
            operation=record.operation,
            run_id=RunId(record.run_id),
            fingerprint=record.fingerprint,
            created_at=record.created_at,
        )

    def add_receipt(self, receipt: Receipt) -> None:
        self._session.add(
            RequestReceiptRecord(
                id=new_id(),
                actor_id=receipt.actor_id,
                idempotency_key=receipt.idempotency_key,
                operation=receipt.operation,
                run_id=receipt.run_id,
                fingerprint=receipt.fingerprint,
                created_at=receipt.created_at,
            )
        )
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()


def _run_fields(run: Run) -> dict[str, Any]:
    return {
        "project_id": run.project_id,
        "mode": run.mode,
        "status": run.status,
        "stage": run.stage,
        "revision": run.revision,
        "inputs": _inputs_json(run.inputs),
        "model_turns": run.counters.model_turns,
        "tool_calls": run.counters.tool_calls,
        "total_tokens": run.counters.total_tokens,
        "input_tokens": run.totals.input_tokens,
        "output_tokens": run.totals.output_tokens,
        "thinking_tokens": run.totals.thinking_tokens,
        "cost_microusd": run.totals.cost_microusd,
        "clarification_rounds": run.clarification_rounds,
        "history": [_turn_json(turn) for turn in run.history],
        "pending_results": [_result_json(result) for result in run.pending_results],
        "draft": run.draft,
        "problems": list(run.problems),
        "error_code": run.error.code if run.error else None,
        "error_message": run.error.message if run.error else None,
        "error_retryable": run.error.retryable if run.error else None,
        "lease_token": run.lease.token if run.lease else None,
        "lease_expires_at": run.lease.expires_at if run.lease else None,
        "created_by": run.created_by,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def _to_run(record: RunRecord) -> Run:
    error = None
    if record.error_code is not None:
        error = RunError(
            record.error_code, record.error_message or "", bool(record.error_retryable)
        )
    lease = None
    if record.lease_token is not None and record.lease_expires_at is not None:
        lease = Lease(record.lease_token, record.lease_expires_at)
    return Run(
        id=RunId(record.id),
        project_id=ProjectId(record.project_id),
        mode=_run_mode(record.mode),
        status=record.status,
        stage=record.stage,
        revision=record.revision,
        inputs=_inputs_from_json(record.inputs),
        created_by=UserId(record.created_by),
        created_at=record.created_at,
        updated_at=record.updated_at,
        counters=RunCounters(
            model_turns=record.model_turns,
            tool_calls=record.tool_calls,
            total_tokens=record.total_tokens,
        ),
        totals=TokenTotals(
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            thinking_tokens=record.thinking_tokens,
            cost_microusd=record.cost_microusd,
        ),
        clarification_rounds=record.clarification_rounds,
        history=tuple(_turn_from_json(turn) for turn in record.history),
        pending_results=tuple(_result_from_json(result) for result in record.pending_results),
        draft=record.draft,
        problems=tuple(record.problems),
        error=error,
        lease=lease,
    )


def _inputs_json(inputs: RunInputs) -> dict[str, Any]:
    limits = inputs.limits
    return {
        "source_version_ids": [str(v) for v in inputs.source_version_ids],
        "provider": inputs.provider,
        "model_id": inputs.model_id,
        "prompt_version": inputs.prompt_version,
        "schema_version": inputs.schema_version,
        "max_clarification_rounds": inputs.max_clarification_rounds,
        "fallback_reason": inputs.fallback_reason,
        "change": None
        if inputs.change is None
        else {
            "change_request_id": str(inputs.change.change_request_id),
            "base_version_id": str(inputs.change.base_version_id),
            "base_content_hash": inputs.change.base_content_hash,
            "request_version_id": str(inputs.change.request_version_id),
        },
        "limits": {
            "max_turns": limits.max_turns,
            "max_tool_calls": limits.max_tool_calls,
            "max_output_tokens_per_call": limits.max_output_tokens_per_call,
            "max_total_tokens": limits.max_total_tokens,
            "max_cost_microusd": limits.max_cost_microusd,
        },
    }


def _inputs_from_json(data: Mapping[str, Any]) -> RunInputs:
    limits = data["limits"]
    change = data.get("change")
    return RunInputs(
        source_version_ids=tuple(SourceVersionId(UUID(v)) for v in data["source_version_ids"]),
        provider=data["provider"],
        model_id=data["model_id"],
        prompt_version=data["prompt_version"],
        schema_version=data["schema_version"],
        max_clarification_rounds=data["max_clarification_rounds"],
        fallback_reason=data.get("fallback_reason"),
        change=None
        if change is None
        else ChangeInputs(
            change_request_id=UUID(change["change_request_id"]),
            base_version_id=UUID(change["base_version_id"]),
            base_content_hash=change["base_content_hash"],
            request_version_id=UUID(change["request_version_id"]),
        ),
        limits=RunLimits(
            max_turns=limits["max_turns"],
            max_tool_calls=limits["max_tool_calls"],
            max_output_tokens_per_call=limits["max_output_tokens_per_call"],
            max_total_tokens=limits["max_total_tokens"],
            max_cost_microusd=limits["max_cost_microusd"],
        ),
    )


def _turn_json(turn: Turn) -> dict[str, Any]:
    match turn:
        case UserMessage(text=text):
            return {"type": "user", "text": text}
        case ModelTurn(steps=steps):
            return {"type": "model", "steps": [dict(step) for step in steps]}
        case ToolResults(results=results):
            return {"type": "tool_results", "results": [_result_json(r) for r in results]}


def _turn_from_json(data: Mapping[str, Any]) -> Turn:
    match data["type"]:
        case "user":
            return UserMessage(data["text"])
        case "model":
            return ModelTurn(tuple(data["steps"]))
        case _:
            return ToolResults(tuple(_result_from_json(r) for r in data["results"]))


def _result_json(result: ToolResult) -> dict[str, Any]:
    return {
        "call_id": result.call_id,
        "name": result.name,
        "output": dict(result.output),
        "is_error": result.is_error,
    }


def _result_from_json(data: Mapping[str, Any]) -> ToolResult:
    return ToolResult(data["call_id"], data["name"], data["output"], bool(data["is_error"]))


def _step_kind(value: str) -> StepKind:
    match value:
        case "tool" | "event":
            return value
        case _:
            return "model_call"


def _run_mode(value: str) -> RunMode:
    match value:
        case "reply" | "change":
            return value
        case _:
            return "initial"


def _to_question(record: QuestionRecord) -> Question:
    return Question(
        id=QuestionId(record.id),
        run_id=RunId(record.run_id),
        round=record.round,
        call_id=record.call_id,
        subject=record.subject,
        text=record.text,
        why_it_matters=record.why_it_matters,
        block_labels=tuple(record.block_labels),
        status=record.status,
        answer=record.answer,
        answer_label=record.answer_label,
        answered_by=None if record.answered_by is None else UserId(record.answered_by),
        answered_at=record.answered_at,
    )


def _claim_json(claim: Claim) -> dict[str, Any]:
    return {
        "text": claim.text,
        "basis": claim.basis,
        "citations": [
            {
                "quote": c.quote,
                "source_version_id": _optional_str(c.source_version_id),
                "block_id": _optional_str(c.block_id),
                "question_id": _optional_str(c.question_id),
            }
            for c in claim.citations
        ],
    }


def _optional_str(value: UUID | None) -> str | None:
    return None if value is None else str(value)


def _optional_uuid(value: str | None) -> UUID | None:
    return None if value is None else UUID(value)


def _to_claim(data: Mapping[str, Any]) -> Claim:
    citations = tuple(
        CitedPassage(
            quote=c["quote"],
            source_version_id=_optional_uuid(c["source_version_id"]),
            block_id=_optional_uuid(c["block_id"]),
            question_id=None if c["question_id"] is None else QuestionId(UUID(c["question_id"])),
        )
        for c in data["citations"]
    )
    return Claim(data["text"], "cited" if data["basis"] == "cited" else "agent", citations)


def _to_message(record: MessageRecord) -> Message:
    return Message(
        id=MessageId(record.id),
        project_id=ProjectId(record.project_id),
        role=record.role,
        kind=record.kind,
        text=record.text,
        created_at=record.created_at,
        author_id=None if record.author_id is None else UserId(record.author_id),
        author_name=record.author_name,
        run_id=None if record.run_id is None else RunId(record.run_id),
        question_id=None if record.question_id is None else QuestionId(record.question_id),
        event=record.event,
        claims=tuple(_to_claim(claim) for claim in record.claims),
        change_request_id=record.change_request_id,
        baseline_version=record.baseline_version,
    )


def _to_suggestion(record: SuggestionRecord) -> Suggestion:
    return Suggestion(
        message_id=MessageId(record.message_id),
        project_id=ProjectId(record.project_id),
        proposed=ProposedSuggestion(
            kind=_suggestion_kind(record.kind),
            request_text=record.request_text,
            version_id=record.version_id,
            decision_id=record.decision_id,
            decision_subject=record.decision_subject,
            answer=record.answer,
        ),
        created_at=record.created_at,
        status=_suggestion_status(record.status),
        revision=record.revision,
        decided_by=None if record.decided_by is None else UserId(record.decided_by),
        decided_at=record.decided_at,
    )


def _suggestion_kind(value: str) -> SuggestionKind:
    match value:
        case "change_request" | "answer_decision" | "start_draft":
            return value
        case _:
            raise ValueError(f"Unknown suggestion kind {value!r}")


def _suggestion_status(value: str) -> SuggestionStatus:
    match value:
        case "offered" | "accepted" | "dismissed":
            return value
        case _:
            raise ValueError(f"Unknown suggestion status {value!r}")
