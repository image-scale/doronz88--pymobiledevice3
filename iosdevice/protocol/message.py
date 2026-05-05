"""DTX message representation for encoding and decoding complete messages."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from bpylist2 import archiver

from .constants import MessageType, TransportFlags, MESSAGE_HEADER_SIZE
from .exceptions import ProtocolError
from .message_aux import AuxData


@dataclass(repr=False)
class Message:
    """A complete DTX message ready for transmission or after parsing.

    The aux_data and payload_data fields hold raw wire bytes. Use the aux
    and payload properties for lazy-decoded, cached Python objects.
    """

    type: MessageType
    aux_data: memoryview = field(default_factory=lambda: memoryview(b""))
    payload_data: memoryview = field(default_factory=lambda: memoryview(b""))

    identifier: int = 0
    conversation_index: int = 0
    channel_code: int = 0
    flags: int = 0
    transport_flags: TransportFlags = TransportFlags.NONE

    # Cached decoded values
    _aux_cache: Optional[list] = field(default=None, init=False, repr=False)
    _aux_error: Optional[Exception] = field(default=None, init=False, repr=False)
    _payload_cache: Any = field(default=None, init=False, repr=False)
    _payload_decoded: bool = field(default=False, init=False, repr=False)
    _payload_error: Optional[Exception] = field(default=None, init=False, repr=False)

    @property
    def aux(self) -> Sequence[Any]:
        """Decoded auxiliary arguments (lazy, cached)."""
        if self._aux_cache is None and self._aux_error is None:
            try:
                self._aux_cache = AuxData.parse(self.aux_data)
            except Exception as e:
                self._aux_error = e

        if self._aux_error is not None:
            raise ProtocolError(f"Failed to decode aux args: {self._aux_error}") from self._aux_error

        return self._aux_cache or []

    @aux.setter
    def aux(self, args: Sequence[Any]) -> None:
        """Set auxiliary arguments and encode to wire format."""
        try:
            self.aux_data = memoryview(AuxData.build(list(args)))
        except Exception as e:
            raise ProtocolError(f"Failed to encode aux args: {e}") from e
        self._aux_cache = list(args)
        self._aux_error = None

    @property
    def payload(self) -> Any:
        """Decoded payload object (lazy, cached)."""
        if len(self.payload_data) > 0 and not self._payload_decoded and self._payload_error is None:
            try:
                self._payload_cache = archiver.unarchive(self.payload_data)
            except Exception as e:
                self._payload_error = e
            self._payload_decoded = True

        if self._payload_error is not None:
            raise ProtocolError(f"Failed to decode payload: {self._payload_error}") from self._payload_error

        return self._payload_cache

    @payload.setter
    def payload(self, obj: Any) -> None:
        """Set payload object and encode to wire format."""
        if obj is None:
            self.payload_data = memoryview(b"")
        else:
            try:
                self.payload_data = memoryview(archiver.archive(obj))
            except Exception as e:
                raise ProtocolError(f"Failed to encode payload: {e}") from e
        self._payload_cache = obj
        self._payload_decoded = True
        self._payload_error = None

    def validate(self) -> None:
        """Validate message according to protocol rules.

        Raises:
            ProtocolError: If the message violates protocol constraints.
        """
        # OK messages must have no payload and no aux data
        if self.type == MessageType.OK:
            if len(self.payload_data) > 0 or len(self.aux_data) > 0:
                raise ProtocolError("OK messages must have no payload and no aux data")

        # ERROR messages must have payload and no aux data
        if self.type == MessageType.ERROR:
            if len(self.payload_data) == 0:
                raise ProtocolError("ERROR messages must have a payload")
            if len(self.aux_data) > 0:
                raise ProtocolError("ERROR messages must have no aux data")

        # Replies (conversation_index != 0) have additional constraints
        if self.conversation_index != 0:
            if self.identifier == 0:
                raise ProtocolError("Reply messages must have non-zero identifier")
            if self.type not in (MessageType.OK, MessageType.OBJECT, MessageType.ERROR):
                raise ProtocolError(f"Reply messages must have type OK/OBJECT/ERROR, got {self.type.name}")

    def chunks(self) -> list[memoryview]:
        """Return wire format as list of memoryviews: [header, aux, payload].

        Raises:
            ProtocolError: If the message is invalid or has unsupported type.
        """
        if self.type not in (
            MessageType.OK,
            MessageType.DATA,
            MessageType.DISPATCH,
            MessageType.OBJECT,
            MessageType.ERROR,
        ):
            raise ProtocolError(f"Unsupported message type for serialization: {self.type.name}")

        self.validate()

        total_size = len(self.aux_data) + len(self.payload_data)
        header = struct.pack(
            "<BBBBIII",
            int(self.type),  # msg_type
            0,  # flags_a
            0,  # flags_b
            0,  # reserved
            len(self.aux_data),  # aux_size
            total_size,  # total_size
            self.flags,  # flags
        )
        # Pad to MESSAGE_HEADER_SIZE (16 bytes)
        if len(header) < MESSAGE_HEADER_SIZE:
            header = header + b"\x00" * (MESSAGE_HEADER_SIZE - len(header))

        return [memoryview(header), self.aux_data, self.payload_data]

    def __repr__(self) -> str:
        payload_repr = None
        aux_repr = None

        try:
            payload_repr = self.payload
        except Exception as e:
            payload_repr = f"<decode error: {e}>"

        try:
            aux_repr = self.aux
        except Exception as e:
            aux_repr = f"<decode error: {e}>"

        expects = "e" if TransportFlags.EXPECTS_REPLY in self.transport_flags else ""
        return (
            f"<Message: i{self.identifier}.{self.conversation_index}{expects} "
            f"c{self.channel_code} type:{self.type.name} "
            f"payload:{payload_repr} aux:{aux_repr}>"
        )
