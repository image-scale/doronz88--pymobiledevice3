"""USBMux exceptions."""


class MuxError(Exception):
    """Base exception for USBMux operations."""
    pass


class DeviceNotFoundError(MuxError):
    """Raised when a requested device is not found."""

    def __init__(self, udid: str = None):
        self.udid = udid
        if udid:
            super().__init__(f"Device not found: {udid}")
        else:
            super().__init__("No device found")


class ConnectionFailedError(MuxError):
    """Raised when a connection to a device fails."""

    def __init__(self, message: str = "Connection failed", port: int = None):
        self.port = port
        super().__init__(message)


class NoDeviceConnectedError(MuxError):
    """Raised when no devices are connected."""

    def __init__(self):
        super().__init__("No devices connected")
