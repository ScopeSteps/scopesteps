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


class SourceTypeMismatchError(UnsupportedMediaTypeError):
    """The file's content is not the type its name says, such as a renamed .doc or image."""

    code = "SOURCE_TYPE_MISMATCH"


class UnreadableSourceError(InvalidInputError):
    code = "SOURCE_UNREADABLE"


class SourcePasswordProtectedError(InvalidInputError):
    code = "SOURCE_PASSWORD_PROTECTED"


class ScannedSourceError(InvalidInputError):
    """A PDF with no text layer: pictures of pages, which would need text recognition."""

    code = "SOURCE_SCANNED"


class SourceTooLargeUnpackedError(InvalidInputError):
    """Small as sent but too large once opened: a compressed file that expands too far, or too
    many pages."""

    code = "SOURCE_TOO_LARGE_UNPACKED"


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
