from scopesteps.kernel.errors import (
    ConflictError,
    InvalidInputError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)


class UnsupportedSourceTypeError(UnsupportedMediaTypeError):
    code = "UNSUPPORTED_SOURCE_TYPE"


class SourceTooLargeError(PayloadTooLargeError):
    code = "SOURCE_TOO_LARGE"


class SourceWordLimitError(PayloadTooLargeError):
    code = "SOURCE_WORD_LIMIT_EXCEEDED"


class UnreadableSourceError(InvalidInputError):
    code = "SOURCE_UNREADABLE"


class EmptySourceError(InvalidInputError):
    code = "SOURCE_EMPTY"


class IdempotencyKeyReusedError(ConflictError):
    code = "IDEMPOTENCY_KEY_REUSED"


class ConcurrentUploadError(ConflictError):
    code = "UPLOAD_IN_PROGRESS"
    retryable = True


class NoSourceFilesError(InvalidInputError):
    code = "SOURCE_FILES_MISSING"


class TooManySourceFilesError(InvalidInputError):
    code = "TOO_MANY_SOURCE_FILES"


class SourceRemovedError(ConflictError):
    code = "SOURCE_REMOVED"


class SourceInUseError(ConflictError):
    code = "SOURCE_IN_USE"


class SourceChangedError(ConflictError):
    code = "SOURCE_CHANGED"
    retryable = True
