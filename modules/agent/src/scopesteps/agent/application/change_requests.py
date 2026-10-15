"""Submitting a change request: the request, its text as evidence and the change run that analyses
it are stored in one transaction before anything is sent to a model (ADR 0011).

It is reached from the conversation (a message sent as a change request) and from run creation
(mode change); both pass the baseline the requester saw, which must still be the current one.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from scopesteps.agent.application.changing import CHANGE_PROMPT_VERSION, CHANGE_SCHEMA_VERSION
from scopesteps.agent.application.ports import (
    ChangeRequests,
    ProjectContext,
    Receipt,
    RunStore,
)
from scopesteps.agent.application.runs import (
    AgentRuntime,
    IdempotencyKeyReusedError,
    ModelNotConfiguredError,
)
from scopesteps.agent.domain.conversation import (
    AgentBusyError,
    BaselineChangedError,
    BaselineRequiredError,
    Message,
    MessageKind,
    MessageRole,
    agent_busy,
    clean_message_text,
)
from scopesteps.agent.domain.ids import MessageId, RunId
from scopesteps.agent.domain.run import (
    ADVANCEABLE,
    ChangeInputs,
    Run,
    RunInputs,
    RunStage,
    RunStatus,
)
from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.change_control.client import OpenChangeRequest
from scopesteps.identity.client import ProjectAccess, Role
from scopesteps.kernel.errors import ConflictError
from scopesteps.kernel.ids import new_id

CREATE_OPERATION = "create"


@dataclass(frozen=True)
class SubmitChange:
    idempotency_key: str
    text: str
    base_version_id: UUID
    base_content_hash: str
    operation: str
    """The receipt's operation, so a retry is recognised by the route it came through."""
    fingerprint: str


@dataclass(frozen=True)
class SubmittedChange:
    message: Message
    run: Run


def submit_change_request(
    store: RunStore,
    audit: AuditRecorder,
    context: ProjectContext,
    requests: ChangeRequests,
    runtime: AgentRuntime,
    access: ProjectAccess,
    command: SubmitChange,
    now: datetime,
) -> SubmittedChange:
    """Record the request against the baseline the requester saw and create the change run that
    analyses it. The caller has checked the role and replayed a retried request.

    Refused with 409 `BASELINE_REQUIRED` before any baseline exists, `BASELINE_CHANGED` when the
    named baseline or its content hash is not the current baseline's, and `AGENT_BUSY` while any
    run is created or running or another change request is being analysed.
    """
    access.require_role(Role.EDITOR)
    # Held to the same limits as a message (ADR 0010).
    text = clean_message_text(command.text)
    baseline = context.baseline(access.project_id)
    if baseline is None:
        raise BaselineRequiredError("A change can be requested once a baseline has been approved.")
    current = baseline.version
    if current.id != command.base_version_id or current.content_hash != command.base_content_hash:
        raise BaselineChangedError(
            "The baseline changed since you opened it. Reload it and send the request again.",
            details={
                "current_baseline_id": str(current.id),
                "content_hash": current.content_hash,
            },
        )
    busy = store.active_run(access.project_id)
    if busy is not None and (busy.status in ADVANCEABLE or busy.mode == "change"):
        raise agent_busy(busy)
    primary = runtime.primary
    if primary is None:
        raise ModelNotConfiguredError("No model provider is configured (MODEL_PROVIDER)")
    # Two requests sent at once both see no work in progress; only one may take the turn.
    if not store.claim_turn(access.project_id):
        raise AgentBusyError("Another request was sent at the same time. Wait for it.")
    served, fallback_reason = primary, None
    if runtime.fallback is not None and runtime.breaker.is_open():
        served, fallback_reason = runtime.fallback, "primary_circuit_open"

    request_version = requests.record_text(access.project_id, text, access.actor.user_id, now)
    run_id = RunId(new_id())
    opened = requests.open(
        OpenChangeRequest(
            project_id=access.project_id,
            text=text,
            requested_by=access.actor.user_id,
            requested_by_name=access.actor.display_name,
            base_version_id=current.id,
            base_content_hash=current.content_hash,
            source_version_id=request_version,
            run_id=run_id,
        ),
        now,
    )
    run = Run(
        id=run_id,
        project_id=access.project_id,
        mode="change",
        status=RunStatus.CREATED,
        stage=RunStage.EXPLORE,
        revision=1,
        inputs=RunInputs(
            # The exact sources the baseline was made from, then the request's text.
            source_version_ids=(*current.source_version_ids, request_version),
            provider=served.provider_name,
            model_id=served.model_id,
            fallback_reason=fallback_reason,
            prompt_version=CHANGE_PROMPT_VERSION,
            schema_version=CHANGE_SCHEMA_VERSION,
            limits=runtime.limits,
            max_clarification_rounds=runtime.max_clarification_rounds,
            change=ChangeInputs(
                change_request_id=opened.id,
                base_version_id=current.id,
                base_content_hash=current.content_hash,
                request_version_id=request_version,
            ),
        ),
        created_by=access.actor.user_id,
        created_at=now,
        updated_at=now,
    )
    message = Message(
        id=MessageId(new_id()),
        project_id=access.project_id,
        role=MessageRole.USER,
        kind=MessageKind.CHANGE_REQUEST,
        text=text,
        created_at=now,
        author_id=access.actor.user_id,
        author_name=access.actor.display_name,
        run_id=run.id,
    )
    store.add_run(run)
    store.add_messages([message])
    store.add_receipt(
        Receipt(
            actor_id=access.actor.user_id,
            idempotency_key=command.idempotency_key,
            operation=command.operation,
            run_id=run.id,
            fingerprint=command.fingerprint,
            created_at=now,
        )
    )
    audit.record(
        project_id=access.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.CHANGE_REQUESTED,
        subjects=(
            Subject(SubjectKind.CHANGE_REQUEST, opened.id),
            Subject(SubjectKind.RUN, run.id),
            Subject(SubjectKind.MESSAGE, message.id),
        ),
        summary=f"Requested change CR-{opened.number} against baseline v{baseline.number}",
        occurred_at=now,
    )
    store.commit()
    return SubmittedChange(message, run)


@dataclass(frozen=True)
class CreateChangeRun:
    idempotency_key: str
    request_text: str
    base_version_id: UUID
    base_content_hash: str


def create_change_run(
    store: RunStore,
    audit: AuditRecorder,
    context: ProjectContext,
    requests: ChangeRequests,
    runtime: AgentRuntime,
    access: ProjectAccess,
    command: CreateChangeRun,
    now: datetime,
) -> Run:
    """`POST /projects/{id}/runs` in change mode: the same request a change request message
    makes. A retry with the same Idempotency-Key returns the run the first one created."""
    access.require_role(Role.EDITOR)
    fingerprint = change_fingerprint(
        CREATE_OPERATION,
        [command.request_text, str(command.base_version_id), command.base_content_hash],
    )
    receipt = store.find_receipt(access.actor.user_id, command.idempotency_key)
    if receipt is not None:
        if receipt.operation != CREATE_OPERATION or receipt.fingerprint != fingerprint:
            raise IdempotencyKeyReusedError(
                "This Idempotency-Key was already used for another request"
            )
        run = store.get_run(receipt.run_id)
        if run is None:
            raise ConflictError("The request with this Idempotency-Key did not store a run")
        return run
    submitted = submit_change_request(
        store,
        audit,
        context,
        requests,
        runtime,
        access,
        SubmitChange(
            idempotency_key=command.idempotency_key,
            text=command.request_text,
            base_version_id=command.base_version_id,
            base_content_hash=command.base_content_hash,
            operation=CREATE_OPERATION,
            fingerprint=fingerprint,
        ),
        now,
    )
    return submitted.run


def change_fingerprint(operation: str, parts: list[str]) -> str:
    return hashlib.sha256(json.dumps([operation, *parts]).encode()).hexdigest()
