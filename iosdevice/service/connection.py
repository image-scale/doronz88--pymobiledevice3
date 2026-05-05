"""TCP/TLS service connection for iOS device communication."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import plistlib
import socket
import ssl
import struct
from enum import Enum
from typing import Any, Optional, Union

from .exceptions import ConnectionClosedError, PlistParseError

# Defaults
DEFAULT_TIMEOUT_SEC = 1.0
SSL_HANDSHAKE_TIMEOUT_SEC = 10.0
STREAM_CLOSE_TIMEOUT_SEC = 1.0


def encode_plist(
    data: dict,
    endianity: str = ">",
    fmt: Enum = plistlib.FMT_XML,
) -> bytes:
    """Encode a dictionary to plist bytes with a length prefix.

    Args:
        data: Dictionary to encode.
        endianity: Byte order for the length prefix ('>' big, '<' little).
        fmt: Plist format (XML or binary).

    Returns:
        Length-prefixed plist bytes.
    """
    payload = plistlib.dumps(data, fmt=fmt)
    header = struct.pack(endianity + "L", len(payload))
    return header + payload


def decode_plist(data: bytes) -> dict:
    """Decode plist bytes to a dictionary.

    Args:
        data: Raw plist bytes (without length prefix).

    Returns:
        Parsed dictionary.

    Raises:
        PlistParseError: If the data cannot be parsed.
    """
    try:
        return plistlib.loads(data)
    except plistlib.InvalidFileException as e:
        # Try filtering invalid XML characters
        filtered = bytes([b for b in data if b >= 0x20 or b in (0x09, 0x0A, 0x0D)])
        try:
            return plistlib.loads(filtered)
        except Exception:
            raise PlistParseError(data, e) from e
    except Exception as e:
        raise PlistParseError(data, e) from e


async def _close_writer(
    writer: asyncio.StreamWriter,
    timeout: float = STREAM_CLOSE_TIMEOUT_SEC,
) -> None:
    """Close a stream writer gracefully with timeout."""
    with contextlib.suppress(Exception):
        writer.close()
    with contextlib.suppress(Exception):
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=timeout)
        except asyncio.TimeoutError:
            with contextlib.suppress(Exception):
                if writer.transport is not None:
                    writer.transport.abort()


class ServiceConnection:
    """Wrapper for TCP connections to iOS device services.

    Supports both synchronous and asynchronous I/O, plist serialization,
    and SSL/TLS upgrades for secure communication.
    """

    def __init__(self, sock: socket.socket) -> None:
        """Initialize with an existing socket.

        Args:
            sock: Connected socket to wrap.
        """
        self._logger = logging.getLogger(__name__)
        self._socket = sock
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._start_future: Optional[asyncio.Future] = None
        self._lock = asyncio.Lock()

        # TLS version bounds
        self._min_tls = ssl.TLSVersion.TLSv1_2
        self._max_tls = ssl.TLSVersion.TLSv1_3

        # Set non-blocking for async operations
        self._socket.setblocking(False)

    @property
    def socket(self) -> Optional[socket.socket]:
        """The underlying socket (may be None if closed)."""
        return self._socket

    @property
    def is_connected(self) -> bool:
        """Check if the connection is open."""
        return self._socket is not None and self._socket.fileno() != -1

    @property
    def is_started(self) -> bool:
        """Check if async streams are initialized."""
        return self._reader is not None and self._writer is not None

    # ----------------------------------------------------------------
    # Factory methods
    # ----------------------------------------------------------------

    @staticmethod
    async def connect_tcp(
        host: str,
        port: int,
        timeout: float = DEFAULT_TIMEOUT_SEC,
    ) -> "ServiceConnection":
        """Create a connection to a TCP endpoint.

        Args:
            host: Hostname or IP address.
            port: Port number.
            timeout: Connection timeout in seconds.

        Returns:
            Connected ServiceConnection.
        """
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        sock = writer.get_extra_info("socket")
        if sock is None:
            await _close_writer(writer)
            raise ConnectionError(f"Failed to get socket for {host}:{port}")

        conn = ServiceConnection(sock)
        conn._reader = reader
        conn._writer = writer
        return conn

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def start(self) -> None:
        """Initialize async streams for the socket.

        This binds the socket to the event loop. Called automatically
        by async methods if needed.
        """
        if self._reader is not None and self._writer is not None:
            return
        if self._socket is None:
            raise ConnectionClosedError("Socket is closed")
        self._reader, self._writer = await asyncio.open_connection(sock=self._socket)

    async def _ensure_started(self) -> None:
        """Ensure async streams are initialized (thread-safe)."""
        if self._reader is not None and self._writer is not None:
            return
        if self._start_future is not None:
            return await self._start_future
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._start_future = fut
        try:
            await self.start()
            fut.set_result(None)
        except BaseException as e:
            self._start_future = None
            if isinstance(e, asyncio.CancelledError):
                fut.cancel()
            else:
                fut.set_exception(e)
            raise

    async def close(self) -> None:
        """Close the connection and release resources."""
        try:
            if self._writer is not None:
                await _close_writer(self._writer)
            if self._socket is not None and self._socket.fileno() != -1:
                with contextlib.suppress(Exception):
                    self._socket.close()
        finally:
            self._socket = None
            self._reader = None
            self._writer = None
            self._start_future = None

    async def __aenter__(self) -> "ServiceConnection":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    # ----------------------------------------------------------------
    # Low-level sync I/O
    # ----------------------------------------------------------------

    def recv_sync(self, size: int = 4096) -> bytes:
        """Receive up to size bytes synchronously.

        Args:
            size: Maximum bytes to receive.

        Returns:
            Received bytes (may be less than size).

        Raises:
            ConnectionClosedError: If the connection is closed.
        """
        if self._socket is None:
            raise ConnectionClosedError("Not connected")
        try:
            self._socket.setblocking(True)
            return self._socket.recv(size)
        except (ssl.SSLError, BrokenPipeError, ConnectionResetError) as e:
            raise ConnectionClosedError() from e
        finally:
            if self._socket is not None:
                self._socket.setblocking(False)

    def sendall_sync(self, data: bytes) -> None:
        """Send all bytes synchronously.

        Args:
            data: Bytes to send.

        Raises:
            ConnectionClosedError: If the connection is closed.
        """
        if self._socket is None:
            raise ConnectionClosedError("Not connected")
        try:
            self._socket.setblocking(True)
            self._socket.sendall(data)
        except (ssl.SSLEOFError, BrokenPipeError, ConnectionResetError) as e:
            raise ConnectionClosedError() from e
        finally:
            if self._socket is not None:
                self._socket.setblocking(False)

    def recvall_sync(self, size: int) -> bytes:
        """Receive exactly size bytes synchronously.

        Args:
            size: Exact number of bytes to receive.

        Returns:
            Received bytes.

        Raises:
            ConnectionClosedError: If the connection closes before all bytes arrive.
        """
        data = b""
        while len(data) < size:
            chunk = self.recv_sync(size - len(data))
            if not chunk:
                raise ConnectionClosedError("Connection closed during recv")
            data += chunk
        return data

    def recv_prefixed_sync(self, endianity: str = ">") -> bytes:
        """Receive a length-prefixed message synchronously.

        Args:
            endianity: Byte order for the length field.

        Returns:
            Message payload (without length prefix).
        """
        header = self.recvall_sync(4)
        if len(header) != 4:
            return b""
        length = struct.unpack(endianity + "L", header)[0]
        return self.recvall_sync(length)

    def recv_plist_sync(self, endianity: str = ">") -> dict:
        """Receive and decode a plist synchronously.

        Args:
            endianity: Byte order for the length prefix.

        Returns:
            Decoded plist as dictionary.
        """
        return decode_plist(self.recv_prefixed_sync(endianity))

    def send_plist_sync(
        self,
        data: dict,
        endianity: str = ">",
        fmt: Enum = plistlib.FMT_XML,
    ) -> None:
        """Encode and send a plist synchronously.

        Args:
            data: Dictionary to send.
            endianity: Byte order for the length prefix.
            fmt: Plist format.
        """
        self.sendall_sync(encode_plist(data, endianity, fmt))

    # ----------------------------------------------------------------
    # Low-level async I/O
    # ----------------------------------------------------------------

    async def recv(self, size: int = 4096) -> bytes:
        """Receive up to size bytes asynchronously.

        Args:
            size: Maximum bytes to receive.

        Returns:
            Received bytes.
        """
        await self._ensure_started()
        return await self._reader.read(size)

    async def sendall(self, data: bytes) -> None:
        """Send all bytes asynchronously.

        Args:
            data: Bytes to send.

        Raises:
            ConnectionClosedError: If the connection is closed.
        """
        await self._ensure_started()
        try:
            self._writer.write(data)
            await self._writer.drain()
        except (ssl.SSLEOFError, BrokenPipeError, ConnectionResetError) as e:
            raise ConnectionClosedError() from e

    async def recvall(self, size: int) -> bytes:
        """Receive exactly size bytes asynchronously.

        Args:
            size: Exact number of bytes to receive.

        Returns:
            Received bytes.

        Raises:
            ConnectionClosedError: If connection closes before all bytes arrive.
        """
        await self._ensure_started()
        try:
            return await self._reader.readexactly(size)
        except asyncio.IncompleteReadError as e:
            raise ConnectionClosedError("Connection closed during recv") from e

    async def recv_prefixed(self, endianity: str = ">") -> bytes:
        """Receive a length-prefixed message asynchronously.

        Args:
            endianity: Byte order for the length field.

        Returns:
            Message payload (without length prefix).
        """
        header = await self.recvall(4)
        length = struct.unpack(endianity + "L", header)[0]
        return await self.recvall(length)

    async def send_prefixed(self, data: bytes, endianity: str = ">") -> None:
        """Send a length-prefixed message asynchronously.

        Args:
            data: Message payload.
            endianity: Byte order for the length prefix.
        """
        header = struct.pack(endianity + "L", len(data))
        await self.sendall(header + data)

    # ----------------------------------------------------------------
    # Plist async I/O
    # ----------------------------------------------------------------

    async def recv_plist(self, endianity: str = ">") -> dict:
        """Receive and decode a plist asynchronously.

        Args:
            endianity: Byte order for the length prefix.

        Returns:
            Decoded plist as dictionary.
        """
        return decode_plist(await self.recv_prefixed(endianity))

    async def send_plist(
        self,
        data: dict,
        endianity: str = ">",
        fmt: Enum = plistlib.FMT_XML,
    ) -> None:
        """Encode and send a plist asynchronously.

        Args:
            data: Dictionary to send.
            endianity: Byte order for the length prefix.
            fmt: Plist format.
        """
        await self.sendall(encode_plist(data, endianity, fmt))

    async def send_recv_plist(
        self,
        data: dict,
        endianity: str = ">",
        fmt: Enum = plistlib.FMT_XML,
    ) -> dict:
        """Send a plist and receive the response atomically.

        This method uses a lock to ensure thread-safety when multiple
        coroutines share the same connection.

        Args:
            data: Dictionary to send.
            endianity: Byte order for the length prefix.
            fmt: Plist format.

        Returns:
            Decoded response plist.
        """
        async with self._lock:
            await self.send_plist(data, endianity, fmt)
            return await self.recv_plist(endianity)

    # ----------------------------------------------------------------
    # SSL/TLS
    # ----------------------------------------------------------------

    def _create_ssl_context(
        self,
        certfile: str,
        keyfile: Optional[str] = None,
    ) -> ssl.SSLContext:
        """Create an SSL context for TLS connections.

        Args:
            certfile: Path to certificate file.
            keyfile: Path to key file (optional, may be in certfile).

        Returns:
            Configured SSL context.
        """
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = self._min_tls
        ctx.maximum_version = self._max_tls

        # Configure ciphers for compatibility
        if ssl.OPENSSL_VERSION.lower().startswith("openssl"):
            ctx.set_ciphers("ALL:!aNULL:!eNULL:@SECLEVEL=0")
        else:
            ctx.set_ciphers("ALL:!aNULL:!eNULL")

        # Legacy compatibility option
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT

        # Disable certificate verification (device certs are self-signed)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        ctx.load_cert_chain(certfile, keyfile)
        return ctx

    def ssl_upgrade_sync(
        self,
        certfile: str,
        keyfile: Optional[str] = None,
    ) -> None:
        """Upgrade the connection to TLS synchronously.

        Args:
            certfile: Path to certificate file.
            keyfile: Path to key file.

        Raises:
            ConnectionClosedError: If the upgrade fails.
        """
        if self._socket is None:
            raise ConnectionClosedError("Not connected")
        try:
            ctx = self._create_ssl_context(certfile, keyfile)
            self._socket.settimeout(SSL_HANDSHAKE_TIMEOUT_SEC)
            self._socket = ctx.wrap_socket(self._socket)
        except OSError as e:
            raise ConnectionClosedError("SSL handshake failed") from e
        finally:
            if self._socket is not None:
                self._socket.settimeout(None)
                self._socket.setblocking(False)

    async def ssl_upgrade(
        self,
        certfile: str,
        keyfile: Optional[str] = None,
    ) -> None:
        """Upgrade the connection to TLS asynchronously.

        Args:
            certfile: Path to certificate file.
            keyfile: Path to key file.

        Raises:
            ConnectionClosedError: If the upgrade fails.
        """
        if self._socket is None:
            raise ConnectionClosedError("Not connected")

        ctx = self._create_ssl_context(certfile, keyfile)

        try:
            if self._reader is None:
                # Not yet bound to event loop - create SSL streams directly
                self._reader, self._writer = await asyncio.open_connection(
                    sock=self._socket,
                    ssl=ctx,
                    server_hostname="",
                    ssl_handshake_timeout=SSL_HANDSHAKE_TIMEOUT_SEC,
                )
            else:
                # Already bound - upgrade in-place
                await self._ensure_started()
                if hasattr(self._writer, "start_tls"):
                    await asyncio.wait_for(
                        self._writer.start_tls(
                            sslcontext=ctx,
                            server_hostname="",
                            ssl_handshake_timeout=SSL_HANDSHAKE_TIMEOUT_SEC,
                        ),
                        timeout=SSL_HANDSHAKE_TIMEOUT_SEC,
                    )
                else:
                    # Fallback for older Python
                    loop = asyncio.get_running_loop()
                    protocol = self._writer._protocol
                    transport = await asyncio.wait_for(
                        loop.start_tls(
                            self._writer.transport,
                            protocol,
                            ctx,
                            server_side=False,
                            server_hostname="",
                            ssl_handshake_timeout=SSL_HANDSHAKE_TIMEOUT_SEC,
                        ),
                        timeout=SSL_HANDSHAKE_TIMEOUT_SEC,
                    )
                    self._writer = asyncio.StreamWriter(
                        transport, protocol, self._reader, loop
                    )
        except OSError as e:
            raise ConnectionClosedError("SSL upgrade failed") from e
