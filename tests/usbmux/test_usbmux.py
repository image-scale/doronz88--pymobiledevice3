"""Tests for USBMux device and connection."""

import pytest

from iosdevice.usbmux.device import MuxDevice
from iosdevice.usbmux.exceptions import (
    MuxError,
    DeviceNotFoundError,
    ConnectionFailedError,
    NoDeviceConnectedError,
)
from iosdevice.usbmux.connection import MuxConnection, get_default_socket_address


class TestMuxDevice:
    """Tests for MuxDevice dataclass."""

    def test_basic_construction(self):
        """MuxDevice should store basic fields."""
        device = MuxDevice(
            device_id=1,
            udid="abc123",
            serial="SN001",
            connection_type="USB",
        )
        assert device.device_id == 1
        assert device.udid == "abc123"
        assert device.serial == "SN001"
        assert device.connection_type == "USB"

    def test_default_values(self):
        """MuxDevice should have sensible defaults."""
        device = MuxDevice(device_id=1, udid="test")
        assert device.serial == ""
        assert device.connection_type == "USB"
        assert device.product_id == 0
        assert device.location_id == 0

    def test_from_plist_basic(self):
        """from_plist should parse device dictionary."""
        plist = {
            "DeviceID": 42,
            "Properties": {
                "SerialNumber": "abc123def456",
                "ConnectionType": "USB",
                "ProductID": 4779,
                "LocationID": 123456,
            }
        }
        device = MuxDevice.from_plist(plist)
        assert device.device_id == 42
        assert device.udid == "abc123def456"
        assert device.connection_type == "USB"
        assert device.product_id == 4779

    def test_from_plist_flat(self):
        """from_plist should handle flat dictionary."""
        plist = {
            "DeviceID": 1,
            "SerialNumber": "flat_udid",
            "ConnectionType": "Network",
        }
        device = MuxDevice.from_plist(plist)
        assert device.device_id == 1
        assert device.udid == "flat_udid"
        assert device.connection_type == "Network"

    def test_is_usb(self):
        """is_usb should return True for USB devices."""
        usb_device = MuxDevice(device_id=1, udid="usb", connection_type="USB")
        network_device = MuxDevice(device_id=2, udid="net", connection_type="Network")

        assert usb_device.is_usb is True
        assert usb_device.is_network is False
        assert network_device.is_usb is False
        assert network_device.is_network is True

    def test_is_network(self):
        """is_network should return True for network devices."""
        network_device = MuxDevice(device_id=1, udid="net", connection_type="Network")
        assert network_device.is_network is True
        assert network_device.is_usb is False

    def test_matches_udid(self):
        """matches should filter by UDID."""
        device = MuxDevice(device_id=1, udid="target123")

        assert device.matches(udid="target123") is True
        assert device.matches(udid="other456") is False
        assert device.matches(udid=None) is True

    def test_matches_connection_type(self):
        """matches should filter by connection type."""
        usb_device = MuxDevice(device_id=1, udid="dev", connection_type="USB")
        network_device = MuxDevice(device_id=2, udid="dev2", connection_type="Network")

        assert usb_device.matches(connection_type="USB") is True
        assert usb_device.matches(connection_type="Network") is False
        assert usb_device.matches(connection_type=None) is True

        assert network_device.matches(connection_type="network") is True  # case insensitive

    def test_matches_combined(self):
        """matches should handle multiple criteria."""
        device = MuxDevice(device_id=1, udid="abc", connection_type="USB")

        assert device.matches(udid="abc", connection_type="USB") is True
        assert device.matches(udid="abc", connection_type="Network") is False
        assert device.matches(udid="xyz", connection_type="USB") is False


class TestMuxExceptions:
    """Tests for USBMux exceptions."""

    def test_mux_error(self):
        """MuxError should be basic exception."""
        error = MuxError("test error")
        assert str(error) == "test error"

    def test_device_not_found_with_udid(self):
        """DeviceNotFoundError should include UDID."""
        error = DeviceNotFoundError("abc123")
        assert error.udid == "abc123"
        assert "abc123" in str(error)

    def test_device_not_found_without_udid(self):
        """DeviceNotFoundError without UDID should work."""
        error = DeviceNotFoundError()
        assert error.udid is None
        assert "No device" in str(error)

    def test_connection_failed_with_port(self):
        """ConnectionFailedError should include port."""
        error = ConnectionFailedError("Failed", port=62078)
        assert error.port == 62078
        assert "Failed" in str(error)

    def test_no_device_connected(self):
        """NoDeviceConnectedError message."""
        error = NoDeviceConnectedError()
        assert "No devices connected" in str(error)


class TestDefaultSocketAddress:
    """Tests for get_default_socket_address."""

    def test_returns_address(self):
        """Should return an address."""
        address = get_default_socket_address()
        assert address is not None

    def test_unix_or_tcp(self):
        """Address should be either Unix path or TCP tuple."""
        import sys
        address = get_default_socket_address()

        if sys.platform == "win32":
            assert isinstance(address, tuple)
            assert len(address) == 2
        else:
            assert isinstance(address, str)
            assert "usbmuxd" in address


class TestMuxConnection:
    """Tests for MuxConnection class."""

    def test_initial_state(self):
        """Connection should start disconnected."""
        conn = MuxConnection()
        assert conn.is_connected is False

    def test_custom_address(self):
        """Should accept custom address."""
        conn = MuxConnection(address="/custom/path")
        assert conn._address == "/custom/path"

    def test_custom_tcp_address(self):
        """Should accept TCP address tuple."""
        conn = MuxConnection(address=("localhost", 12345))
        assert conn._address == ("localhost", 12345)


class TestMuxConnectionProtocol:
    """Tests for MuxConnection protocol handling."""

    def test_next_tag_increments(self):
        """_next_tag should return incrementing values."""
        conn = MuxConnection()
        tag1 = conn._next_tag()
        tag2 = conn._next_tag()
        tag3 = conn._next_tag()

        assert tag1 == 1
        assert tag2 == 2
        assert tag3 == 3

    def test_create_socket_unix(self):
        """_create_socket should create appropriate socket type."""
        import socket
        import sys

        conn = MuxConnection(address="/var/run/test")
        if sys.platform != "win32":
            sock = conn._create_socket()
            assert sock.family == socket.AF_UNIX
            sock.close()

    def test_create_socket_tcp(self):
        """_create_socket should create TCP socket for tuple address."""
        import socket

        conn = MuxConnection(address=("localhost", 12345))
        sock = conn._create_socket()
        assert sock.family == socket.AF_INET
        sock.close()


class TestMuxConnectionErrors:
    """Tests for MuxConnection error handling."""

    def test_send_without_connect_raises(self):
        """Sending without connection should raise."""
        conn = MuxConnection()
        with pytest.raises(MuxError, match="Not connected"):
            conn._send_sync({"MessageType": "Test"})

    def test_recv_without_connect_raises(self):
        """Receiving without connection should raise."""
        conn = MuxConnection()
        with pytest.raises(MuxError, match="Not connected"):
            conn._recv_sync()

    @pytest.mark.asyncio
    async def test_async_send_without_connect_raises(self):
        """Async sending without connection should raise."""
        conn = MuxConnection()
        with pytest.raises(MuxError, match="Not connected"):
            await conn._send({"MessageType": "Test"})

    @pytest.mark.asyncio
    async def test_async_recv_without_connect_raises(self):
        """Async receiving without connection should raise."""
        conn = MuxConnection()
        with pytest.raises(MuxError, match="Not connected"):
            await conn._recv()
