"""Why talking to Jira or publishing failed, each with a stable code a screen can explain."""

from scopesteps.kernel.errors import (
    ConflictError,
    InvalidInputError,
    PermissionDeniedError,
    RateLimitedError,
    UnavailableError,
    UpstreamError,
)


class JiraNotConfiguredError(UnavailableError):
    """The server has no key to encrypt API tokens with, so Jira cannot be connected."""

    code = "JIRA_NOT_CONFIGURED"


class JiraNotConnectedError(ConflictError):
    code = "JIRA_NOT_CONNECTED"


class ConnectionChangedError(ConflictError):
    code = "CONNECTION_CHANGED"


class VersionNotApprovedError(ConflictError):
    code = "VERSION_NOT_APPROVED"


class PublishInProgressError(ConflictError):
    code = "PUBLISH_IN_PROGRESS"


class PublishNotRetryableError(ConflictError):
    code = "PUBLISH_NOT_RETRYABLE"


class JiraSiteInvalidError(InvalidInputError):
    code = "JIRA_SITE_INVALID"


class JiraAuthFailedError(InvalidInputError):
    code = "JIRA_AUTH_FAILED"


class JiraForbiddenError(PermissionDeniedError):
    """Jira refused the account, not ScopeSteps the user."""

    code = "JIRA_FORBIDDEN"


class JiraProjectNotFoundError(InvalidInputError):
    code = "JIRA_PROJECT_NOT_FOUND"


class JiraProjectUnsuitableError(InvalidInputError):
    code = "JIRA_PROJECT_UNSUITABLE"


class JiraRateLimitedError(RateLimitedError):
    code = "JIRA_RATE_LIMITED"


class JiraUnavailableError(UpstreamError):
    """No answer, a timeout or a server error: whether Jira acted is unknown."""

    code = "JIRA_UNAVAILABLE"


class JiraRejectedError(UpstreamError):
    """Jira refused one issue's fields; sending the same fields again fails the same way."""

    code = "JIRA_REJECTED"
    retryable = False


class JiraNoDoneStatusError(UpstreamError):
    code = "JIRA_NO_DONE_STATUS"
    retryable = False


ITEM_FAILURES = frozenset(
    {
        JiraRejectedError.code,
        JiraNoDoneStatusError.code,
        "PARENT_NOT_PUBLISHED",
    }
)
"""Codes that fail one item and let the publish go on with the rest."""
