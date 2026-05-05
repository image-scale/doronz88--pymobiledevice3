"""Platform detection and utilities for cross-platform support."""

from __future__ import annotations

import datetime
import os
import socket
import struct
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple, Union

# Default keepalive parameters
DEFAULT_KEEPALIVE_IDLE_SEC = 3
DEFAULT_KEEPALIVE_INTERVAL_SEC = 3
DEFAULT_KEEPALIVE_MAX_FAILS = 3

# Darwin-specific TCP options
_DARWIN_TCP_KEEPALIVE = 0x10
_DARWIN_TCP_KEEPINTVL = 0x101
_DARWIN_TCP_KEEPCNT = 0x102


def is_wsl() -> bool:
    """Check if running under Windows Subsystem for Linux."""
    try:
        with open("/proc/version") as f:
            version = f.read()
            return "Microsoft" in version or "WSL" in version
    except (FileNotFoundError, PermissionError):
        return False


class PlatformUtils(ABC):
    """Abstract base class for platform-specific utilities."""

    _instance: Optional["PlatformUtils"] = None
    _platform_name: str = ""

    @classmethod
    def create(cls) -> "PlatformUtils":
        """Create the appropriate platform utilities instance.

        Returns:
            Platform-specific utilities instance.

        Raises:
            NotImplementedError: If the platform is not supported.
        """
        if cls._instance is not None:
            return cls._instance

        cls._platform_name = sys.platform

        if cls._platform_name == "win32":
            cls._instance = WindowsUtils()
        elif cls._platform_name == "darwin":
            cls._instance = DarwinUtils()
        elif cls._platform_name == "linux":
            cls._instance = WslUtils() if is_wsl() else LinuxUtils()
        elif cls._platform_name == "cygwin":
            cls._instance = CygwinUtils()
        else:
            raise NotImplementedError(f"Unsupported platform: {cls._platform_name}")

        return cls._instance

    @property
    def platform_name(self) -> str:
        """The system platform name."""
        return self._platform_name

    @property
    @abstractmethod
    def is_admin(self) -> bool:
        """Check if running with administrator/root privileges."""
        ...

    @property
    @abstractmethod
    def usbmux_address(self) -> Tuple[Union[str, Tuple[str, int]], int]:
        """Get the usbmuxd socket address and family.

        Returns:
            Tuple of (address, socket_family).
            On Unix, address is a string path to the Unix socket.
            On Windows, address is a tuple (host, port) for TCP.
        """
        ...

    @property
    @abstractmethod
    def pair_record_path(self) -> Path:
        """Path to the lockdown pair records directory."""
        ...

    @property
    @abstractmethod
    def loopback_header(self) -> bytes:
        """Loopback interface packet header for IPv6."""
        ...

    @property
    def admin_prompt(self) -> str:
        """Message to display when admin privileges are required."""
        return "This operation requires elevated privileges."

    def set_keepalive(
        self,
        sock: socket.socket,
        idle_sec: int = DEFAULT_KEEPALIVE_IDLE_SEC,
        interval_sec: int = DEFAULT_KEEPALIVE_INTERVAL_SEC,
        max_fails: int = DEFAULT_KEEPALIVE_MAX_FAILS,
    ) -> None:
        """Configure TCP keepalive on a socket.

        Args:
            sock: Socket to configure.
            idle_sec: Seconds before sending first keepalive probe.
            interval_sec: Seconds between keepalive probes.
            max_fails: Number of failed probes before connection is dropped.
        """
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    def parse_timestamp(self, timestamp: float) -> datetime.datetime:
        """Parse a platform-specific timestamp to datetime.

        Args:
            timestamp: Numeric timestamp value.

        Returns:
            Parsed datetime object.
        """
        return datetime.datetime.fromtimestamp(timestamp)

    def fix_ownership_if_needed(self, path: Path) -> None:
        """Fix file ownership when running with sudo.

        Args:
            path: Path to fix ownership for.
        """
        pass

    def home_directory(self) -> Path:
        """Get the user's home directory."""
        return Path.home()


class PosixUtils(PlatformUtils):
    """Base class for POSIX (Unix-like) systems."""

    # Default Unix socket path for usbmuxd
    USBMUXD_SOCKET = "/var/run/usbmuxd"

    @property
    def is_admin(self) -> bool:
        return os.geteuid() == 0

    @property
    def usbmux_address(self) -> Tuple[str, int]:
        return self.USBMUXD_SOCKET, socket.AF_UNIX

    @property
    def admin_prompt(self) -> str:
        return 'This command requires root privileges. Try running with "sudo".'

    def fix_ownership_if_needed(self, path: Path) -> None:
        sudo_uid = os.getenv("SUDO_UID")
        sudo_gid = os.getenv("SUDO_GID")
        if sudo_uid is not None and sudo_gid is not None:
            os.chown(path, int(sudo_uid), int(sudo_gid))


class DarwinUtils(PosixUtils):
    """macOS-specific utilities."""

    @property
    def pair_record_path(self) -> Path:
        return Path("/var/db/lockdown/")

    @property
    def loopback_header(self) -> bytes:
        # Big-endian AF_INET6 for macOS loopback
        return struct.pack(">I", socket.AF_INET6)

    def set_keepalive(
        self,
        sock: socket.socket,
        idle_sec: int = DEFAULT_KEEPALIVE_IDLE_SEC,
        interval_sec: int = DEFAULT_KEEPALIVE_INTERVAL_SEC,
        max_fails: int = DEFAULT_KEEPALIVE_MAX_FAILS,
    ) -> None:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.IPPROTO_TCP, _DARWIN_TCP_KEEPALIVE, idle_sec)
        sock.setsockopt(socket.IPPROTO_TCP, _DARWIN_TCP_KEEPINTVL, interval_sec)
        sock.setsockopt(socket.IPPROTO_TCP, _DARWIN_TCP_KEEPCNT, max_fails)


class LinuxUtils(PosixUtils):
    """Linux-specific utilities."""

    @property
    def pair_record_path(self) -> Path:
        return Path("/var/lib/lockdown/")

    @property
    def loopback_header(self) -> bytes:
        # Raw Ethernet type for IPv6 (0x86dd)
        return b"\x00\x00\x86\xdd"

    def set_keepalive(
        self,
        sock: socket.socket,
        idle_sec: int = DEFAULT_KEEPALIVE_IDLE_SEC,
        interval_sec: int = DEFAULT_KEEPALIVE_INTERVAL_SEC,
        max_fails: int = DEFAULT_KEEPALIVE_MAX_FAILS,
    ) -> None:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # Use standard Linux TCP keepalive options
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle_sec)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval_sec)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, max_fails)

    def home_directory(self) -> Path:
        # If running with sudo, use the original user's home
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user:
            return Path(f"~{sudo_user}").expanduser()
        return Path.home()


class WslUtils(LinuxUtils):
    """Windows Subsystem for Linux utilities."""

    # WSL uses Windows iTunes TCP endpoint
    ITUNES_HOST = ("127.0.0.1", 27015)

    @property
    def usbmux_address(self) -> Tuple[Tuple[str, int], int]:
        return self.ITUNES_HOST, socket.AF_INET


class CygwinUtils(PosixUtils):
    """Cygwin utilities."""

    ITUNES_HOST = ("127.0.0.1", 27015)

    @property
    def usbmux_address(self) -> Tuple[Tuple[str, int], int]:
        return self.ITUNES_HOST, socket.AF_INET

    @property
    def pair_record_path(self) -> Path:
        return Path(os.environ.get("ALLUSERSPROFILE", ""), "Apple", "Lockdown")

    @property
    def loopback_header(self) -> bytes:
        return b"\x00\x00\x86\xdd"


class WindowsUtils(PlatformUtils):
    """Windows-specific utilities."""

    ITUNES_HOST = ("127.0.0.1", 27015)

    @property
    def is_admin(self) -> bool:
        """Check for administrator privileges on Windows."""
        try:
            # Try to create a file in system directory
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    @property
    def usbmux_address(self) -> Tuple[Tuple[str, int], int]:
        return self.ITUNES_HOST, socket.AF_INET

    @property
    def pair_record_path(self) -> Path:
        return Path(os.environ.get("ALLUSERSPROFILE", ""), "Apple", "Lockdown")

    @property
    def loopback_header(self) -> bytes:
        return b"\x00\x00\x86\xdd"

    @property
    def admin_prompt(self) -> str:
        return 'This command requires administrator privileges. Try running as Administrator.'

    def set_keepalive(
        self,
        sock: socket.socket,
        idle_sec: int = DEFAULT_KEEPALIVE_IDLE_SEC,
        interval_sec: int = DEFAULT_KEEPALIVE_INTERVAL_SEC,
        max_fails: int = DEFAULT_KEEPALIVE_MAX_FAILS,
    ) -> None:
        """Configure TCP keepalive on Windows."""
        # Try to use ioctl for precise control
        target_sock = sock
        if not hasattr(target_sock, "ioctl"):
            target_sock = getattr(sock, "_sock", sock)

        if hasattr(target_sock, "ioctl"):
            try:
                # SIO_KEEPALIVE_VALS: (on/off, idle_ms, interval_ms)
                target_sock.ioctl(
                    socket.SIO_KEEPALIVE_VALS,
                    (1, idle_sec * 1000, interval_sec * 1000),
                )
                return
            except (AttributeError, OSError):
                pass

        # Fallback to basic SO_KEEPALIVE
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    def parse_timestamp(self, timestamp: float) -> datetime.datetime:
        # Windows timestamps are in milliseconds
        return datetime.datetime.fromtimestamp(timestamp / 1000)


def get_platform() -> PlatformUtils:
    """Get the platform utilities instance.

    Returns:
        Platform-specific utilities singleton.
    """
    return PlatformUtils.create()
