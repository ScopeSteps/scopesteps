from scopesteps.kernel.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    UnauthenticatedError,
    UnavailableError,
    UpstreamError,
)


class InvalidCredentialsError(UnauthenticatedError):
    """One response for every failed sign-in, so it never reveals which part was wrong."""

    code = "INVALID_CREDENTIALS"

    def __init__(self) -> None:
        super().__init__("Email or password is incorrect")


class SessionRequiredError(UnauthenticatedError):
    """One response for a missing, unknown, expired and signed-out session alike."""

    def __init__(self) -> None:
        super().__init__("Sign in to continue")


class SignInDisabledError(UnavailableError):
    code = "SIGN_IN_DISABLED"

    def __init__(self) -> None:
        super().__init__("Sign-in is not enabled on this server (AUTH_MODE is not session)")


class EmailNotVerifiedError(PermissionDeniedError):
    """Raised only after the password matched, so it tells a guesser nothing."""

    code = "EMAIL_NOT_VERIFIED"

    def __init__(self) -> None:
        super().__init__(
            "Confirm your email address first: open the link we sent you, or ask for a new one."
        )


class TokenInvalidError(NotFoundError):
    """One response for an unknown, expired and used confirmation link alike."""

    code = "TOKEN_INVALID"

    def __init__(self) -> None:
        super().__init__("This link is not valid any more. Ask for a new one.")


class InvitationInvalidError(NotFoundError):
    """One response for an unknown, expired, used, replaced and cancelled invitation alike."""

    code = "INVITATION_INVALID"

    def __init__(self) -> None:
        super().__init__(
            "This invitation is not valid any more. Ask the person who invited you for a new one."
        )


class InvitationEmailMismatchError(PermissionDeniedError):
    code = "INVITATION_EMAIL_MISMATCH"

    def __init__(self) -> None:
        super().__init__(
            "This invitation is for another email address. Sign out and sign in with that one."
        )


class AccountExistsError(ConflictError):
    code = "ACCOUNT_EXISTS"

    def __init__(self) -> None:
        super().__init__("An account already uses this email address. Sign in to join instead.")


class AlreadyMemberError(ConflictError):
    code = "ALREADY_MEMBER"


class AlreadyInvitedError(ConflictError):
    code = "ALREADY_INVITED"


class MemberChangedError(ConflictError):
    """The member's roles changed since the caller read them."""

    code = "MEMBER_CHANGED"


class LastApproverError(ConflictError):
    code = "LAST_APPROVER"


class RolesInvalidError(InvalidInputError):
    code = "ROLES_INVALID"


class EmailInvalidError(InvalidInputError):
    code = "EMAIL_INVALID"


class TooManyAttemptsError(RateLimitedError):
    def __init__(self) -> None:
        super().__init__("Too many attempts. Wait a while, then try again.")


class EmailFailedError(UpstreamError):
    code = "EMAIL_FAILED"

    def __init__(self) -> None:
        super().__init__("The email could not be sent. Try again later, or copy the link instead.")
