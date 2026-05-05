"""DTX chunk assembler for multi-fragment message reassembly."""

import logging
from collections.abc import AsyncGenerator
from typing import Optional

from .constants import MAX_CHUNK_SIZE, MAX_PAYLOAD_SIZE
from .exceptions import ProtocolError
from .fragment import Chunk


logger = logging.getLogger(__name__)


class ChunkAssembler:
    """Assembles multiple chunks into a complete message buffer.

    The first chunk (index=0, count>1) declares the total payload size
    in its data_size field but carries no body bytes. We pre-allocate a
    buffer of that size and write subsequent chunks into it as they arrive.

    Zero-copy assembly is achieved when chunks arrive in index order -
    the pre-allocated buffer is returned directly. If chunks arrive out
    of order, we log a debug message and create a sorted copy.

    Memory limits are checked at construction time before allocating.

    Usage:
        first_chunk = ...  # index=0, count>1
        assembler = ChunkAssembler(first_chunk, current_buffered=0, max_buffered=MAX_PAYLOAD_SIZE)

        for chunk in subsequent_chunks:
            if assembler.add(chunk):
                buffer, metadata = assembler.assemble()
                process_message(buffer, metadata)
    """

    def __init__(
        self,
        first_chunk: Chunk,
        current_buffered: int,
        max_buffered_size: int,
    ) -> None:
        """Initialize assembler with the first (header-only) chunk.

        Args:
            first_chunk: The first chunk declaring total message size.
            current_buffered: Bytes already buffered by other assemblers.
            max_buffered_size: Maximum total buffered bytes allowed.

        Raises:
            ProtocolError: If the declared size is invalid or exceeds limits.
        """
        total = first_chunk.data_size

        if total == 0:
            raise ProtocolError(
                f"Multi-chunk message {first_chunk.identifier} has data_size=0 "
                f"in the first chunk; cannot pre-allocate assembly buffer"
            )

        if total > MAX_PAYLOAD_SIZE:
            raise ProtocolError(
                f"Multi-chunk message {first_chunk.identifier} declares total size "
                f"{total} which exceeds MAX_MESSAGE_SIZE {MAX_PAYLOAD_SIZE}"
            )

        if current_buffered + total > max_buffered_size:
            raise ProtocolError(
                f"Pre-allocating {total} bytes for message {first_chunk.identifier} "
                f"would exceed MAX_BUFFERED_SIZE {max_buffered_size}"
            )

        self._first = first_chunk
        self._expected_count: int = first_chunk.count - 1  # body chunks only
        self._buffer = bytearray(total)
        self._write_offset: int = 0
        # Track (chunk_index, buffer_offset, length) for each body chunk
        self._slots: list[tuple[int, int, int]] = []
        self._seen_indices: set[int] = set()

    @property
    def identifier(self) -> int:
        """Message identifier from the first chunk."""
        return self._first.identifier

    @property
    def declared_size(self) -> int:
        """Total payload bytes as declared by the first chunk."""
        return len(self._buffer)

    def add(self, chunk: Chunk) -> bool:
        """Add a body chunk's payload to the assembly buffer.

        The payload bytes are written immediately at the current write
        offset. A slot record is stored to track arrival order.

        Args:
            chunk: A non-first chunk with payload data.

        Returns:
            True if all body chunks have arrived and assemble() can be called.

        Raises:
            ProtocolError: On duplicate index, missing payload, or overflow.
        """
        if chunk.payload is None:
            raise ProtocolError(
                f"Non-first chunk {chunk.index} of message {self._first.identifier} has no payload"
            )

        if chunk.index in self._seen_indices:
            raise ProtocolError(
                f"Duplicate chunk index {chunk.index} for message {self._first.identifier}"
            )

        n = len(chunk.payload)
        if self._write_offset + n > len(self._buffer):
            raise ProtocolError(
                f"Chunk {chunk.index} of message {self._first.identifier} would write "
                f"{self._write_offset + n} bytes total, exceeding declared size {len(self._buffer)}"
            )

        # Copy payload into buffer
        self._buffer[self._write_offset:self._write_offset + n] = chunk.payload
        self._slots.append((chunk.index, self._write_offset, n))
        self._write_offset += n
        self._seen_indices.add(chunk.index)

        return len(self._slots) == self._expected_count

    def assemble(self) -> tuple[bytearray, Chunk]:
        """Return the assembled buffer and first chunk metadata.

        In the common case (in-order arrival), the pre-allocated buffer
        is returned directly (zero-copy). For out-of-order arrivals,
        a sorted copy is created.

        Returns:
            A tuple of (assembled_buffer, first_chunk_metadata).

        Raises:
            AssertionError: If called before all chunks have arrived.
            ProtocolError: If assembled bytes don't match declared size.
        """
        assert len(self._slots) == self._expected_count, (
            "assemble() called before all chunks arrived"
        )

        if self._write_offset != len(self._buffer):
            raise ProtocolError(
                f"Assembled {self._write_offset} bytes but first chunk of message "
                f"{self._first.identifier} declared total size {len(self._buffer)}"
            )

        # Check if chunks arrived in order
        arrived_indices = [s[0] for s in self._slots]
        sorted_slots = sorted(self._slots, key=lambda s: s[0])
        sorted_indices = [s[0] for s in sorted_slots]

        if arrived_indices != sorted_indices:
            logger.debug(
                "Message %d: chunks arrived out of order %s, reordering into fresh buffer",
                self._first.identifier,
                arrived_indices,
            )
            # Create a new buffer with properly ordered data
            result = bytearray(len(self._buffer))
            write_pos = 0
            for _, src_offset, length in sorted_slots:
                result[write_pos:write_pos + length] = self._buffer[src_offset:src_offset + length]
                write_pos += length

            if write_pos != len(result):
                raise ProtocolError(
                    f"Assembled {write_pos} bytes but first chunk declared "
                    f"{len(result)} for message {self._first.identifier}"
                )
            self._slots = sorted_slots
            self._buffer = result

        return self._buffer, self._first

    @staticmethod
    async def split_payload(*payload: memoryview) -> AsyncGenerator[Chunk, None]:
        """Split payload chunks into transmittable Chunk objects.

        For payloads <= MAX_CHUNK_SIZE, a single chunk is yielded.
        For larger payloads, a header-only chunk (index=0) is yielded first,
        followed by body chunks with actual data.

        Zero-copy is used when possible - body chunks that fit entirely
        within a source chunk are returned as sub-memoryviews.

        Args:
            *payload: One or more memoryview objects to concatenate and split.

        Yields:
            Chunk objects ready for transmission.

        Raises:
            ProtocolError: If total payload exceeds MAX_PAYLOAD_SIZE.
        """
        total_size = sum(len(p) for p in payload)

        if total_size > MAX_PAYLOAD_SIZE:
            raise ProtocolError(
                f"Cannot split payload of size {total_size} which exceeds "
                f"MAX_MESSAGE_SIZE {MAX_PAYLOAD_SIZE}"
            )

        # Single-chunk fast path
        if total_size <= MAX_CHUNK_SIZE:
            if len(payload) == 1:
                # Perfect zero-copy: use the source memoryview directly
                chunk_payload: memoryview = payload[0]
            elif total_size == 0:
                chunk_payload = memoryview(b"")
            else:
                # Concatenate multiple small chunks
                buf = bytearray(total_size)
                offset = 0
                for chunk in payload:
                    n = len(chunk)
                    buf[offset:offset + n] = chunk
                    offset += n
                chunk_payload = memoryview(buf)

            yield Chunk(index=0, count=1, data_size=total_size, payload=chunk_payload)
            return

        # Multi-chunk path
        body_count = (total_size + MAX_CHUNK_SIZE - 1) // MAX_CHUNK_SIZE
        count = body_count + 1  # +1 for header-only chunk at index 0

        # Yield header-only first chunk
        yield Chunk(index=0, count=count, data_size=total_size, payload=memoryview(b""))

        # Track position in source chunks
        src_idx: int = 0
        src_off: int = 0

        for body_i in range(body_count):
            # Skip exhausted source chunks
            while src_idx < len(payload) and src_off >= len(payload[src_idx]):
                src_off -= len(payload[src_idx])
                src_idx += 1

            chunk_start = body_i * MAX_CHUNK_SIZE
            chunk_end = min(chunk_start + MAX_CHUNK_SIZE, total_size)
            chunk_size = chunk_end - chunk_start

            # How many bytes remain in current source chunk?
            available = len(payload[src_idx]) - src_off

            if available >= chunk_size:
                # Zero-copy: entire body chunk fits in current source chunk
                chunk_payload = payload[src_idx][src_off:src_off + chunk_size]
                src_off += chunk_size
            else:
                # Boundary chunk: spans multiple source chunks
                buf = bytearray(chunk_size)
                buf_off = 0
                remaining = chunk_size
                while remaining > 0:
                    take = min(len(payload[src_idx]) - src_off, remaining)
                    buf[buf_off:buf_off + take] = payload[src_idx][src_off:src_off + take]
                    buf_off += take
                    src_off += take
                    remaining -= take
                    if src_off >= len(payload[src_idx]):
                        src_idx += 1
                        src_off = 0
                chunk_payload = memoryview(buf)

            yield Chunk(index=body_i + 1, count=count, data_size=chunk_size, payload=chunk_payload)
