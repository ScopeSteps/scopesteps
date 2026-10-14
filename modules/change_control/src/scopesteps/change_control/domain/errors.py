from scopesteps.kernel.errors import ConflictError


class BaselineChangedError(ConflictError):
    """The project's baseline is not the one the caller expected, or not the one the draft was
    made from; nothing from this request was saved."""

    code = "BASELINE_CHANGED"


class ApprovalBlockedError(ConflictError):
    """At least one approval check failed; `details.checks` has every result."""

    code = "APPROVAL_BLOCKED"


class DecisionInProgressError(ConflictError):
    """A concurrent decision on the same version or baseline, or with the same Idempotency-Key,
    was committed first; nothing from this request was saved."""

    code = "DECISION_IN_PROGRESS"
    retryable = True


class IdempotencyKeyReusedError(ConflictError):
    code = "IDEMPOTENCY_KEY_REUSED"
