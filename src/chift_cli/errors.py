SUCCESS = 0
ARGUMENT_ERROR = 2
AUTHENTICATION_ERROR = 3
RETRY_RECOMMENDED = 4


class ChiftCliError(Exception):
    exit_code = ARGUMENT_ERROR

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationError(ChiftCliError):
    exit_code = AUTHENTICATION_ERROR


class RetryRecommendedError(ChiftCliError):
    exit_code = RETRY_RECOMMENDED
