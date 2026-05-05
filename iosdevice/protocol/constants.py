"""Protocol constants for DTX communication."""

from enum import IntEnum, IntFlag


# Maximum byte size of any single assembled message (128 MiB)
MAX_PAYLOAD_SIZE: int = 128 * 1024 * 1024

# Maximum byte size of a single chunk body (128 KiB)
MAX_CHUNK_SIZE: int = 128 * 1024

# Magic number for chunk headers
CHUNK_MAGIC: int = 0x1F3D5B79

# Minimum chunk header size in bytes
CHUNK_HEADER_SIZE: int = 32

# Per-message payload header size
MESSAGE_HEADER_SIZE: int = 16


class TransportFlags(IntFlag):
    """Bit flags in the chunk header flags field."""
    NONE = 0
    EXPECTS_REPLY = 1 << 0


class MessageType(IntEnum):
    """Message type codes used in the DTX payload header."""
    OK = 0           # Acknowledgment response with no payload
    DATA = 1         # Raw data transfer
    DISPATCH = 2     # Method invocation (selector call)
    OBJECT = 3       # Archived object payload
    ERROR = 4        # Error response with NSError payload
    BARRIER = 5      # Synchronization barrier
    PRIMITIVE = 6    # Primitive value
    COMPRESSED = 7   # Compressed payload
    PROXIED = 8      # Proxied message
