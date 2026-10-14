from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.orm import Session

from scopesteps.agent.application.ports import Passage, Receipt
from scopesteps.agent.domain.budget import RunCounters, RunLimits
from scopesteps.agent.domain.ids import QuestionId, RunId, StepId
from scopesteps.agent.domain.model import ModelTurn, ToolResult, ToolResults, Turn, UserMessage
from scopesteps.agent.domain.run import (
    Lease,
    Question,
    Run,
    RunError,
    RunInputs,
    RunStep,
    StepKind,
    TokenTotals,
)
from scopesteps.agent.infrastructure.orm import (
    QuestionRecord,
    RequestReceiptRecord,
    RunRecord,
    RunStepRecord,
)
from scopesteps.backlog.client import CandidateProposal, candidate_problems, save_candidate
from scopesteps.identity.client import UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceVersionId, load_passages, removed_versions


class SqlPassageReader:
    def __init__(self, session: Session) -> None:
        self._session = session

    def load(self, project_id: ProjectId, version_ids: Sequence[UUID]) -> list[Passage]:
        return [
            Passage(
                block_id=passage.block_id,
                source_version_id=passage.source_version_id,
                source_kind=passage.source_kind,
                ordinal=passage.ordinal,
                text=passage.text,
            )
            for passage in load_passages(
                self._session, project_id, [SourceVersionId(v) for v in version_ids]
            )
        ]

    def removed(self, project_id: ProjectId, version_ids: Sequence[UUID]) -> set[UUID]:
        return set(
            removed_versions(self._session, project_id, [SourceVersionId(v) for v in version_ids])
        )


class SqlCandidateStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def problems(self, proposal: CandidateProposal) -> list[str]:
        return candidate_problems(self._session, proposal)

    def save(self, proposal: CandidateProposal, now: datetime) -> None:
        save_candidate(self._session, proposal, now)


class SqlRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

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
        return [
            Question(
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
            for record in records
        ]

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
        wanted = {str(version_id) for version_id in version_ids}
        rows = self._session.execute(
            select(RunRecord.id, RunRecord.inputs).where(RunRecord.project_id == project_id)
        )
        return [
            RunId(run_id)
            for run_id, inputs in rows
            if wanted.intersection(inputs["source_version_ids"])
        ]

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
        mode="initial",
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
    return RunInputs(
        source_version_ids=tuple(SourceVersionId(UUID(v)) for v in data["source_version_ids"]),
        provider=data["provider"],
        model_id=data["model_id"],
        prompt_version=data["prompt_version"],
        schema_version=data["schema_version"],
        max_clarification_rounds=data["max_clarification_rounds"],
        fallback_reason=data.get("fallback_reason"),
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
