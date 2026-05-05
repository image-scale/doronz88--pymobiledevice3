"""Protocol constants for DTX communication."""

from enum import IntFlag


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
