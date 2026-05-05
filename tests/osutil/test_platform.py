"""Tests for OS platform utilities."""

import datetime
import socket
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from iosdevice.osutil.platform import (
    get_platform,
    PlatformUtils,
    DarwinUtils,
    LinuxUtils,
    WindowsUtils,
    WslUtils,
    CygwinUtils,
    PosixUtils,
    is_wsl,
    DEFAULT_KEEPALIVE_IDLE_SEC,
    DEFAULT_KEEPALIVE_INTERVAL_SEC,
    DEFAULT_KEEPALIVE_MAX_FAILS,
)


class TestIsWsl:
    """Tests for WSL detection."""

    def test_not_wsl_when_no_proc_version(self):
        """Should return False when /proc/version doesn't exist."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            assert is_wsl() is False

    def test_wsl_detected(self):
        """Should detect WSL from /proc/version."""
        mock_file = MagicMock()
        mock_file.__enter__ = lambda s: mock_file
        mock_file.__exit__ = lambda s, *args: None
        mock_file.read.return_value = "Linux version 5.10.102.1-microsoft-standard-WSL2"

        with patch("builtins.open", return_value=mock_file):
            assert is_wsl() is True

    def test_not_wsl_on_regular_linux(self):
        """Should return False on regular Linux."""
        mock_file = MagicMock()
        mock_file.__enter__ = lambda s: mock_file
        mock_file.__exit__ = lambda s, *args: None
        mock_file.read.return_value = "Linux version 5.15.0-generic"

        with patch("builtins.open", return_value=mock_file):
            assert is_wsl() is False


class TestGetPlatform:
    """Tests for platform factory."""

    def test_returns_platform_utils(self):
        """Should return a PlatformUtils instance."""
        # Reset singleton for testing
        PlatformUtils._instance = None

        with patch("sys.platform", "linux"):
            with patch("iosdevice.osutil.platform.is_wsl", return_value=False):
                result = get_platform()
                assert isinstance(result, PlatformUtils)

    def test_singleton(self):
        """Should return same instance on repeated calls."""
        PlatformUtils._instance = None

        with patch("sys.platform", "linux"):
            with patch("iosdevice.osutil.platform.is_wsl", return_value=False):
                first = get_platform()
                second = get_platform()
                assert first is second

    def test_linux_platform(self):
        """Should create LinuxUtils for Linux."""
        PlatformUtils._instance = None

        with patch("sys.platform", "linux"):
            with patch("iosdevice.osutil.platform.is_wsl", return_value=False):
                result = PlatformUtils.create()
                assert isinstance(result, LinuxUtils)

    def test_darwin_platform(self):
        """Should create DarwinUtils for macOS."""
        PlatformUtils._instance = None

        with patch("sys.platform", "darwin"):
            result = PlatformUtils.create()
            assert isinstance(result, DarwinUtils)

    def test_win32_platform(self):
        """Should create WindowsUtils for Windows."""
        PlatformUtils._instance = None

        with patch("sys.platform", "win32"):
            result = PlatformUtils.create()
            assert isinstance(result, WindowsUtils)

    def test_wsl_platform(self):
        """Should create WslUtils for WSL."""
        PlatformUtils._instance = None

        with patch("sys.platform", "linux"):
            with patch("iosdevice.osutil.platform.is_wsl", return_value=True):
                result = PlatformUtils.create()
                assert isinstance(result, WslUtils)

    def test_cygwin_platform(self):
        """Should create CygwinUtils for Cygwin."""
        PlatformUtils._instance = None

        with patch("sys.platform", "cygwin"):
            result = PlatformUtils.create()
            assert isinstance(result, CygwinUtils)

    def test_unsupported_platform(self):
        """Should raise for unsupported platforms."""
        PlatformUtils._instance = None

        with patch("sys.platform", "freebsd12"):
            with pytest.raises(NotImplementedError, match="freebsd12"):
                PlatformUtils.create()


class TestDarwinUtils:
    """Tests for macOS utilities."""

    def test_usbmux_address(self):
        """Should use Unix socket for usbmuxd."""
        utils = DarwinUtils()
        addr, family = utils.usbmux_address
        assert addr == "/var/run/usbmuxd"
        assert family == socket.AF_UNIX

    def test_pair_record_path(self):
        """Should use /var/db/lockdown."""
        utils = DarwinUtils()
        assert utils.pair_record_path == Path("/var/db/lockdown/")

    def test_loopback_header(self):
        """Should return big-endian AF_INET6."""
        utils = DarwinUtils()
        header = utils.loopback_header
        assert len(header) == 4
        # Big-endian AF_INET6 (30 on macOS)
        import struct
        assert struct.unpack(">I", header)[0] == socket.AF_INET6

    def test_set_keepalive(self):
        """Should configure Darwin TCP keepalive options."""
        utils = DarwinUtils()
        sock = MagicMock()

        utils.set_keepalive(sock)

        # Should enable SO_KEEPALIVE
        sock.setsockopt.assert_any_call(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # Should set TCP options
        assert sock.setsockopt.call_count == 4

    def test_is_admin_as_root(self):
        """Should return True when running as root."""
        utils = DarwinUtils()
        with patch("os.geteuid", return_value=0):
            assert utils.is_admin is True

    def test_is_admin_as_user(self):
        """Should return False when not root."""
        utils = DarwinUtils()
        with patch("os.geteuid", return_value=1000):
            assert utils.is_admin is False


class TestLinuxUtils:
    """Tests for Linux utilities."""

    def test_usbmux_address(self):
        """Should use Unix socket for usbmuxd."""
        utils = LinuxUtils()
        addr, family = utils.usbmux_address
        assert addr == "/var/run/usbmuxd"
        assert family == socket.AF_UNIX

    def test_pair_record_path(self):
        """Should use /var/lib/lockdown."""
        utils = LinuxUtils()
        assert utils.pair_record_path == Path("/var/lib/lockdown/")

    def test_loopback_header(self):
        """Should return IPv6 ethertype."""
        utils = LinuxUtils()
        assert utils.loopback_header == b"\x00\x00\x86\xdd"

    def test_set_keepalive(self):
        """Should configure Linux TCP keepalive options."""
        utils = LinuxUtils()
        sock = MagicMock()

        utils.set_keepalive(sock, idle_sec=5, interval_sec=2, max_fails=10)

        sock.setsockopt.assert_any_call(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt.assert_any_call(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5)
        sock.setsockopt.assert_any_call(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 2)
        sock.setsockopt.assert_any_call(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 10)

    def test_home_directory_with_sudo(self):
        """Should use original user's home when running with sudo."""
        utils = LinuxUtils()
        with patch.dict("os.environ", {"SUDO_USER": "testuser"}):
            with patch("pathlib.Path.expanduser") as mock_expand:
                mock_expand.return_value = Path("/home/testuser")
                home = utils.home_directory()
                assert home == Path("/home/testuser")

    def test_home_directory_without_sudo(self):
        """Should use current home without sudo."""
        utils = LinuxUtils()
        with patch.dict("os.environ", {}, clear=True):
            home = utils.home_directory()
            assert isinstance(home, Path)


class TestWindowsUtils:
    """Tests for Windows utilities."""

    def test_usbmux_address(self):
        """Should use TCP for iTunes."""
        utils = WindowsUtils()
        addr, family = utils.usbmux_address
        assert addr == ("127.0.0.1", 27015)
        assert family == socket.AF_INET

    def test_pair_record_path(self):
        """Should use Apple Lockdown in ALLUSERSPROFILE."""
        utils = WindowsUtils()
        with patch.dict("os.environ", {"ALLUSERSPROFILE": "C:\\ProgramData"}):
            path = utils.pair_record_path
            assert "Apple" in str(path)
            assert "Lockdown" in str(path)

    def test_loopback_header(self):
        """Should return IPv6 ethertype."""
        utils = WindowsUtils()
        assert utils.loopback_header == b"\x00\x00\x86\xdd"

    def test_parse_timestamp_milliseconds(self):
        """Should parse timestamps in milliseconds."""
        utils = WindowsUtils()
        # 1000 ms = 1 second after epoch
        dt = utils.parse_timestamp(1000)
        assert dt.year == 1970
        assert dt.second == 1

    def test_set_keepalive_fallback(self):
        """Should fall back to SO_KEEPALIVE when ioctl unavailable."""
        utils = WindowsUtils()
        sock = MagicMock(spec=["setsockopt"])
        # No ioctl attribute

        utils.set_keepalive(sock)

        sock.setsockopt.assert_called_with(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    def test_admin_prompt(self):
        """Should mention Administrator."""
        utils = WindowsUtils()
        assert "Administrator" in utils.admin_prompt


class TestWslUtils:
    """Tests for WSL utilities."""

    def test_usbmux_address(self):
        """Should use TCP for iTunes on Windows host."""
        utils = WslUtils()
        addr, family = utils.usbmux_address
        assert addr == ("127.0.0.1", 27015)
        assert family == socket.AF_INET

    def test_inherits_linux_pair_path(self):
        """Should inherit Linux pair record path."""
        utils = WslUtils()
        assert utils.pair_record_path == Path("/var/lib/lockdown/")


class TestCygwinUtils:
    """Tests for Cygwin utilities."""

    def test_usbmux_address(self):
        """Should use TCP for iTunes."""
        utils = CygwinUtils()
        addr, family = utils.usbmux_address
        assert addr == ("127.0.0.1", 27015)
        assert family == socket.AF_INET

    def test_loopback_header(self):
        """Should return IPv6 ethertype."""
        utils = CygwinUtils()
        assert utils.loopback_header == b"\x00\x00\x86\xdd"


class TestPosixUtils:
    """Tests for POSIX base class."""

    def test_fix_ownership_with_sudo(self):
        """Should chown when running with sudo."""
        utils = LinuxUtils()
        mock_path = MagicMock()

        with patch.dict("os.environ", {"SUDO_UID": "1000", "SUDO_GID": "1000"}):
            with patch("os.chown") as mock_chown:
                utils.fix_ownership_if_needed(mock_path)
                mock_chown.assert_called_once_with(mock_path, 1000, 1000)

    def test_fix_ownership_without_sudo(self):
        """Should do nothing without sudo."""
        utils = LinuxUtils()
        mock_path = MagicMock()

        with patch.dict("os.environ", {}, clear=True):
            with patch("os.chown") as mock_chown:
                utils.fix_ownership_if_needed(mock_path)
                mock_chown.assert_not_called()


class TestPlatformUtilsBase:
    """Tests for base PlatformUtils class."""

    def test_parse_timestamp(self):
        """Should parse Unix timestamp."""
        # Use a concrete implementation
        utils = LinuxUtils()
        dt = utils.parse_timestamp(0)
        assert dt.year == 1970
        assert dt.month == 1
        assert dt.day == 1

    def test_home_directory(self):
        """Should return home path."""
        # Use a concrete implementation
        utils = DarwinUtils()
        home = utils.home_directory()
        assert isinstance(home, Path)

    def test_platform_name(self):
        """Should store platform name."""
        PlatformUtils._instance = None
        PlatformUtils._platform_name = ""

        with patch("sys.platform", "linux"):
            with patch("iosdevice.osutil.platform.is_wsl", return_value=False):
                utils = PlatformUtils.create()
                assert utils.platform_name == "linux"


class TestDefaultKeepaliveConstants:
    """Tests for keepalive default constants."""

    def test_idle_default(self):
        """Should have sensible idle default."""
        assert DEFAULT_KEEPALIVE_IDLE_SEC == 3

    def test_interval_default(self):
        """Should have sensible interval default."""
        assert DEFAULT_KEEPALIVE_INTERVAL_SEC == 3

    def test_max_fails_default(self):
        """Should have sensible max fails default."""
        assert DEFAULT_KEEPALIVE_MAX_FAILS == 3
