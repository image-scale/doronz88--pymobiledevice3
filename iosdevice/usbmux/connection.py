"""USB Mux connection handling."""

from __future__ import annotations

import asyncio
import plistlib
import socket
import struct
import sys
from typing import Optional, List

from .device import MuxDevice
from .exceptions import MuxError, DeviceNotFoundError, ConnectionFailedError


# Mux protocol constants
MUX_PROTOCOL_VERSION = 1
MUX_TAG_PLIST = 8

# Message types
MSG_RESULT = "Result"
MSG_DEVICE_LIST = "DeviceList"
MSG_DEVICE_ATTACHED = "Attached"
MSG_DEVICE_DETACHED = "Detached"


def get_default_socket_address() -> tuple:
    """Get the default usbmuxd socket address for the current platform.

    Returns:
        A tuple suitable for socket.connect():
        - Unix: A string path to the socket file
        - Windows: A tuple of (host, port)
    """
    if sys.platform == "win32":
        return ("127.0.0.1", 27015)
    else:
        return "/var/run/usbmuxd"


class MuxConnection:
    """Connection to the usbmuxd daemon for device enumeration and proxying.

    This class handles the plist-based protocol used by modern usbmuxd
    (as opposed to the older binary protocol).
    """

    def __init__(self, address: Optional[str | tuple] = None):
        """Initialize a MuxConnection.

        Args:
            address: Socket address to connect to. If None, uses platform default.
        """
        self._address = address or get_default_socket_address()
        self._socket: Optional[socket.socket] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._tag = 0

    @property
    def is_connected(self) -> bool:
        """Whether the connection is currently open."""
        return self._socket is not None or self._writer is not None

    def _next_tag(self) -> int:
        """Get the next message tag."""
        self._tag += 1
        return self._tag

    def _create_socket(self) -> socket.socket:
        """Create a socket appropriate for the address type."""
        if isinstance(self._address, str):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        return sock

    def connect_sync(self) -> None:
        """Establish a synchronous connection to usbmuxd.

        Raises:
            MuxError: If connection fails.
        """
        if self._socket is not None:
            return

        try:
            self._socket = self._create_socket()
            self._socket.connect(self._address)
        except OSError as e:
            self._socket = None
            raise MuxError(f"Failed to connect to usbmuxd: {e}") from e

    async def connect(self) -> None:
        """Establish an async connection to usbmuxd.

        Raises:
            MuxError: If connection fails.
        """
        if self._writer is not None:
            return

        try:
            if isinstance(self._address, str):
                self._reader, self._writer = await asyncio.open_unix_connection(
                    path=self._address
                )
            else:
                host, port = self._address
                self._reader, self._writer = await asyncio.open_connection(
                    host=host, port=port
                )
        except OSError as e:
            self._reader = None
            self._writer = None
            raise MuxError(f"Failed to connect to usbmuxd: {e}") from e

    def close_sync(self) -> None:
        """Close the synchronous connection."""
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    async def close(self) -> None:
        """Close the async connection."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

    def _send_sync(self, message: dict) -> None:
        """Send a plist message synchronously."""
        if self._socket is None:
            raise MuxError("Not connected")

        payload = plistlib.dumps(message, fmt=plistlib.FMT_XML)
        header = struct.pack("<IIII", len(payload) + 16, MUX_PROTOCOL_VERSION, MUX_TAG_PLIST, message.get("Tag", 0))
        self._socket.sendall(header + payload)

    def _recv_sync(self) -> dict:
        """Receive a plist message synchronously."""
        if self._socket is None:
            raise MuxError("Not connected")

        header = self._socket.recv(16)
        if len(header) < 16:
            raise MuxError("Connection closed")

        length, version, tag_type, tag = struct.unpack("<IIII", header)
        payload_length = length - 16

        if payload_length <= 0:
            return {}

        payload = b""
        while len(payload) < payload_length:
            chunk = self._socket.recv(payload_length - len(payload))
            if not chunk:
                raise MuxError("Connection closed while reading payload")
            payload += chunk

        return plistlib.loads(payload)

    async def _send(self, message: dict) -> None:
        """Send a plist message asynchronously."""
        if self._writer is None:
            raise MuxError("Not connected")

        payload = plistlib.dumps(message, fmt=plistlib.FMT_XML)
        header = struct.pack("<IIII", len(payload) + 16, MUX_PROTOCOL_VERSION, MUX_TAG_PLIST, message.get("Tag", 0))
        self._writer.write(header + payload)
        await self._writer.drain()

    async def _recv(self) -> dict:
        """Receive a plist message asynchronously."""
        if self._reader is None:
            raise MuxError("Not connected")

        header = await self._reader.readexactly(16)
        length, version, tag_type, tag = struct.unpack("<IIII", header)
        payload_length = length - 16

        if payload_length <= 0:
            return {}

        payload = await self._reader.readexactly(payload_length)
        return plistlib.loads(payload)

    def _send_recv_sync(self, message: dict) -> dict:
        """Send a message and wait for response synchronously."""
        message["Tag"] = self._next_tag()
        self._send_sync(message)
        return self._recv_sync()

    async def _send_recv(self, message: dict) -> dict:
        """Send a message and wait for response asynchronously."""
        message["Tag"] = self._next_tag()
        await self._send(message)
        return await self._recv()

    def list_devices_sync(self) -> List[MuxDevice]:
        """List all connected devices synchronously.

        Returns:
            A list of MuxDevice objects.

        Raises:
            MuxError: If listing fails.
        """
        self.connect_sync()
        try:
            response = self._send_recv_sync({
                "MessageType": "ListDevices",
                "ClientVersionString": "iosdevice",
                "ProgName": "iosdevice",
            })

            devices = []
            for device_data in response.get("DeviceList", []):
                devices.append(MuxDevice.from_plist(device_data))
            return devices
        finally:
            self.close_sync()

    async def list_devices(self) -> List[MuxDevice]:
        """List all connected devices asynchronously.

        Returns:
            A list of MuxDevice objects.

        Raises:
            MuxError: If listing fails.
        """
        await self.connect()
        try:
            response = await self._send_recv({
                "MessageType": "ListDevices",
                "ClientVersionString": "iosdevice",
                "ProgName": "iosdevice",
            })

            devices = []
            for device_data in response.get("DeviceList", []):
                devices.append(MuxDevice.from_plist(device_data))
            return devices
        finally:
            await self.close()

    def find_device_sync(
        self,
        udid: Optional[str] = None,
        connection_type: Optional[str] = None,
    ) -> Optional[MuxDevice]:
        """Find a device matching the given criteria synchronously.

        Args:
            udid: UDID to match (None for any device).
            connection_type: Connection type to match (None for any).

        Returns:
            The first matching device, or None if not found.
        """
        devices = self.list_devices_sync()
        for device in devices:
            if device.matches(udid=udid, connection_type=connection_type):
                return device
        return None

    async def find_device(
        self,
        udid: Optional[str] = None,
        connection_type: Optional[str] = None,
    ) -> Optional[MuxDevice]:
        """Find a device matching the given criteria asynchronously.

        Args:
            udid: UDID to match (None for any device).
            connection_type: Connection type to match (None for any).

        Returns:
            The first matching device, or None if not found.
        """
        devices = await self.list_devices()
        for device in devices:
            if device.matches(udid=udid, connection_type=connection_type):
                return device
        return None

    def connect_to_device_sync(
        self,
        device: MuxDevice,
        port: int,
    ) -> socket.socket:
        """Connect to a port on a device synchronously.

        Args:
            device: The device to connect to.
            port: The port number to connect to.

        Returns:
            A connected socket.

        Raises:
            ConnectionFailedError: If connection fails.
        """
        self.connect_sync()
        try:
            # Port must be in network byte order (big-endian)
            port_be = ((port & 0xFF) << 8) | ((port >> 8) & 0xFF)

            response = self._send_recv_sync({
                "MessageType": "Connect",
                "DeviceID": device.device_id,
                "PortNumber": port_be,
                "ClientVersionString": "iosdevice",
                "ProgName": "iosdevice",
            })

            result = response.get("Number", response.get("Result", -1))
            if result != 0:
                raise ConnectionFailedError(
                    f"Connect failed with error {result}", port=port
                )

            # Transfer socket ownership
            sock = self._socket
            self._socket = None
            return sock
        except ConnectionFailedError:
            self.close_sync()
            raise
        except Exception as e:
            self.close_sync()
            raise ConnectionFailedError(str(e), port=port) from e

    async def connect_to_device(
        self,
        device: MuxDevice,
        port: int,
    ) -> socket.socket:
        """Connect to a port on a device asynchronously.

        Note: Returns a regular socket, not an async connection.

        Args:
            device: The device to connect to.
            port: The port number to connect to.

        Returns:
            A connected socket.

        Raises:
            ConnectionFailedError: If connection fails.
        """
        await self.connect()
        try:
            # Port must be in network byte order
            port_be = ((port & 0xFF) << 8) | ((port >> 8) & 0xFF)

            response = await self._send_recv({
                "MessageType": "Connect",
                "DeviceID": device.device_id,
                "PortNumber": port_be,
                "ClientVersionString": "iosdevice",
                "ProgName": "iosdevice",
            })

            result = response.get("Number", response.get("Result", -1))
            if result != 0:
                raise ConnectionFailedError(
                    f"Connect failed with error {result}", port=port
                )

            # Extract underlying socket from writer
            if self._writer is not None:
                sock = self._writer.get_extra_info("socket")
                self._writer = None
                self._reader = None
                return sock
            else:
                raise ConnectionFailedError("No socket available", port=port)
        except ConnectionFailedError:
            await self.close()
            raise
        except Exception as e:
            await self.close()
            raise ConnectionFailedError(str(e), port=port) from e
