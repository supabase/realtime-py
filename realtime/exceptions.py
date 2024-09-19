from typing import Optional


class RealtimeError(Exception):
    """Base class for all exceptions in the Realtime module."""
    pass


class NotConnectedError(RealtimeError):
    """Exception raised when an operation requiring an active connection is attempted without one."""

    def __init__(self, function_name: str):
        """
        Initialize the exception with the function name.

        Args:
            function_name (str): The name of the function that requires an active connection.
        """
        super().__init__(f"The function '{function_name}' requires an active connection.")
        self.function_name: str = function_name


class AuthorizationError(RealtimeError):
    """Exception raised when there is an authorization failure for private channels."""

    def __init__(self, message: Optional[str] = None):
        """
        Initialize the exception with an optional message.

        Args:
            message (Optional[str]): Custom error message.
        """
        default_message = "Authorization failed for private channel."
        super().__init__(message or default_message)
        self.message: str = message or default_message


class ConnectionFailedError(RealtimeError):
    """Exception raised when the client fails to establish a connection."""

    def __init__(self, attempts: int, last_exception: Exception):
        """
        Initialize the exception with the number of attempts and the last exception.

        Args:
            attempts (int): Number of connection attempts made.
            last_exception (Exception): The exception raised during the last attempt.
        """
        message = f"Failed to establish a connection after {attempts} attempts: {last_exception}"
        super().__init__(message)
        self.attempts: int = attempts
        self.last_exception: Exception = last_exception


class ReconnectionFailedError(RealtimeError):
    """Exception raised when the client fails to reconnect after disconnection."""

    def __init__(self, attempts: int, last_exception: Exception):
        """
        Initialize the exception with the number of attempts and the last exception.

        Args:
            attempts (int): Number of reconnection attempts made.
            last_exception (Exception): The exception raised during the last attempt.
        """
        message = f"Failed to reconnect after {attempts} attempts: {last_exception}"
        super().__init__(message)
        self.attempts: int = attempts
        self.last_exception: Exception = last_exception


class InvalidMessageError(RealtimeError):
    """Exception raised when an invalid message is received from the server."""

    def __init__(self, message: str):
        """
        Initialize the exception with the invalid message.

        Args:
            message (str): The invalid message received.
        """
        super().__init__(f"Invalid message received: {message}")
        self.message: str = message