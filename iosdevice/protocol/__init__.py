"""DTX protocol implementation for iOS device communication."""

from .exceptions import ProtocolError
from .constants import MAX_PAYLOAD_SIZE, MAX_CHUNK_SIZE, CHUNK_HEADER_SIZE
from .fragment import Chunk
from .assembler import ChunkAssembler

__all__ = [
    "ProtocolError",
    "MAX_PAYLOAD_SIZE",
    "MAX_CHUNK_SIZE",
    "CHUNK_HEADER_SIZE",
    "Chunk",
    "ChunkAssembler",
]
