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
from .primitives import (
    NULL,
    WireBase,
    WireNull,
    WireString,
    WireBuffer,
    WireInt32,
    WireInt64,
    WireFloat,
    WireDict,
)
from .message_aux import AuxData

__all__ = [
    # Exceptions
    "ProtocolError",
    # Constants
    "MAX_PAYLOAD_SIZE",
    "MAX_CHUNK_SIZE",
    "CHUNK_HEADER_SIZE",
    "MESSAGE_HEADER_SIZE",
    "TransportFlags",
    "MessageType",
    # Fragment/Assembler
    "Chunk",
    "ChunkAssembler",
    # NS Types
    "Error",
    "UniqueID",
    "Null",
    "URL",
    "Value",
    "MutableData",
    "MutableString",
    "Date",
    "TapMessage",
    # Primitive Types
    "NULL",
    "WireBase",
    "WireNull",
    "WireString",
    "WireBuffer",
    "WireInt32",
    "WireInt64",
    "WireFloat",
    "WireDict",
    # Aux Data
    "AuxData",
]
