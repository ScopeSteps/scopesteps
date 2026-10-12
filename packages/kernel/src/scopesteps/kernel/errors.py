"""Expected failures with stable codes. The API maps each class to an HTTP status."""


class DomainError(Exception):
    code: str = "DOMAIN_ERROR"
    retryable: bool = False

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class UnauthenticatedError(DomainError):
    code = "UNAUTHENTICATED"


class PermissionDeniedError(DomainError):
    code = "PERMISSION_DENIED"


class NotFoundError(DomainError):
    code = "NOT_FOUND"


class ConflictError(DomainError):
    code = "CONFLICT"


class FeatureNotImplementedError(DomainError):
    code = "NOT_IMPLEMENTED"

    def __init__(self, feature: str) -> None:
        super().__init__(f"{feature} is not implemented yet", details={"feature": feature})
