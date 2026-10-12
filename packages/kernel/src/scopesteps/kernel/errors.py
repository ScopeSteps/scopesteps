"""Base error type that maps onto the API error envelope."""


class DomainError(Exception):
    """An expected, user-facing failure with a stable machine-readable code."""

    code: str = "DOMAIN_ERROR"
    retryable: bool = False

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
