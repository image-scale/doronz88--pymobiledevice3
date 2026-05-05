"""DTX chunk representation for message fragmentation."""

from dataclasses import dataclass, field
import struct

from .constants import CHUNK_MAGIC, CHUNK_HEADER_SIZE, TransportFlags


@dataclass(repr=False)
class Chunk:
    """A single DTX chunk (fragment) with metadata and optional payload.

    In the DTX protocol, large messages are split into multiple chunks.
    The first chunk (index=0) declares the total message size but carries
    no payload data. Subsequent chunks carry the actual payload bytes.
    """

    index: int
    count: int
    data_size: int
    identifier: int = 0
    conversation_index: int = 0
    channel_code: int = 0
    flags: TransportFlags = TransportFlags.NONE
    payload: memoryview = field(default_factory=lambda: memoryview(b""))

    def chunks(self) -> list[memoryview]:
        """Return list of memoryview chunks for wire transmission.

        Returns:
            A list containing the serialized header and the payload.
        """
        header = struct.pack(
            "<IIHHIIIII",
            CHUNK_MAGIC,
            CHUNK_HEADER_SIZE,
            self.index,
            self.count,
            self.data_size,
            self.identifier,
            self.conversation_index,
            self.channel_code,
            int(self.flags),
        )
        return [memoryview(header), self.payload]

    def __repr__(self) -> str:
        return (
            f"<Chunk: i{self.identifier}.{self.conversation_index} c{self.channel_code} "
            f"index={self.index}/{self.count} flags={self.flags:#x} data_size={self.data_size}>"
        )
