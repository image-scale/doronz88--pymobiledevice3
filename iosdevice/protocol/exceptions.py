"""Protocol exceptions for iOS device communication."""


class ProtocolError(Exception):
    """Raised when the DTX protocol stream contains invalid or unexpected data."""
    pass
