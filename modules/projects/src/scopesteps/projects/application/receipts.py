"""Idempotency receipts for every command the projects module accepts: creating and renaming a
project, correcting a person and confirming their decision rights all share one table."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import ConflictError
from scopesteps.projects.domain.ids import ProjectId


class IdempotencyKeyReusedError(ConflictError):
    code = "IDEMPOTENCY_KEY_REUSED"


@dataclass(frozen=True)
class Receipt:
    """An accepted command, kept so a retry with the same Idempotency-Key does not act twice."""

    actor_id: UserId
    idempotency_key: str
    project_id: ProjectId
    fingerprint: str
    """Covers the operation and every value it was given, so one key cannot serve two commands."""
    created_at: datetime


class ReceiptStore(Protocol):
    def find(self, actor_id: UserId, idempotency_key: str) -> Receipt | None: ...

    def add(self, receipt: Receipt) -> None: ...


def fingerprint(operation: str, project_id: ProjectId | None, *values: str | int | None) -> str:
    canonical = json.dumps([operation, None if project_id is None else str(project_id), *values])
    return hashlib.sha256(canonical.encode()).hexdigest()


def replayed_project(
    receipts: ReceiptStore, actor_id: UserId, idempotency_key: str, command_fingerprint: str
) -> ProjectId | None:
    """The project an earlier, identical command with this key acted on; None if the key is new.

    Raises IdempotencyKeyReusedError if the key was used for a different command.
    """
    receipt = receipts.find(actor_id, idempotency_key)
    if receipt is None:
        return None
    if receipt.fingerprint != command_fingerprint:
        raise IdempotencyKeyReusedError("This Idempotency-Key was already used for another request")
    return receipt.project_id
