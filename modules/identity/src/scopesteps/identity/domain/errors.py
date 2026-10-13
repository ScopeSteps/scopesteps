from scopesteps.kernel.errors import UnauthenticatedError, UnavailableError


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
