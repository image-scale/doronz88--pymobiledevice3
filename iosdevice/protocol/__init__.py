"""DTX protocol implementation for iOS device communication."""

from .exceptions import ProtocolError
from .constants import (
    MAX_PAYLOAD_SIZE,
    MAX_CHUNK_SIZE,
    CHUNK_HEADER_SIZE,
    MESSAGE_HEADER_SIZE,
    TransportFlags,
    MessageType,
)
from .fragment import Chunk
from .assembler import ChunkAssembler
from .ns_types import (
    Error,
    UniqueID,
    Null,
    URL,
    Value,
    MutableData,
    MutableString,
    Date,
    TapMessage,
)

__all__ = [
    "ProtocolError",
    "MAX_PAYLOAD_SIZE",
    "MAX_CHUNK_SIZE",
    "CHUNK_HEADER_SIZE",
    "MESSAGE_HEADER_SIZE",
    "TransportFlags",
    "MessageType",
    "Chunk",
    "ChunkAssembler",
    "Error",
    "UniqueID",
    "Null",
    "URL",
    "Value",
    "MutableData",
    "MutableString",
    "Date",
    "TapMessage",
]
