"""Service connection exceptions."""


class ConnectionError(Exception):
    """Raised when a connection-level error occurs."""
    pass


class ConnectionClosedError(ConnectionError):
    """Raised when the connection is closed unexpectedly."""
    pass


class PlistParseError(ConnectionError):
    """Raised when plist data cannot be parsed."""

    def __init__(self, data: bytes, original_error: Exception = None) -> None:
        self.data = data
        self.original_error = original_error
        preview = data[:50].hex() if data else "(empty)"
        super().__init__(f"Failed to parse plist: {preview}...")
