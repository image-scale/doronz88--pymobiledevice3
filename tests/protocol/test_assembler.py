"""Tests for ChunkAssembler: assembly, splitting, zero-copy, and edge cases."""

import itertools
import pytest

from iosdevice.protocol.exceptions import ProtocolError
from iosdevice.protocol.fragment import Chunk
from iosdevice.protocol.assembler import ChunkAssembler
from iosdevice.protocol.constants import MAX_CHUNK_SIZE, MAX_PAYLOAD_SIZE


def make_first_chunk(total_size: int, count: int = 2, identifier: int = 1) -> Chunk:
    """Build a first (header-only) chunk declaring total_size bytes."""
    return Chunk(
        index=0,
        count=count,
        data_size=total_size,
        identifier=identifier,
    )


def make_body_chunk(index: int, payload: bytes, count: int = 2, identifier: int = 1) -> Chunk:
    """Build a non-first body chunk carrying payload."""
    return Chunk(
        index=index,
        count=count,
        data_size=len(payload),
        identifier=identifier,
        payload=memoryview(bytearray(payload)),
    )


async def collect_chunks(gen) -> list[Chunk]:
    """Drain an async generator of Chunks into a list."""
    return [c async for c in gen]


class TestChunkAssemblerConstruction:
    """Tests for ChunkAssembler construction and validation."""

    def test_basic_construction(self):
        """Test basic assembler construction."""
        first = make_first_chunk(total_size=100, count=3)
        assembler = ChunkAssembler(first, current_buffered=0, max_buffered_size=1024)
        assert assembler.identifier == 1
        assert assembler.declared_size == 100

    def test_zero_data_size_raises(self):
        """Zero data_size in first chunk should raise error."""
        first = make_first_chunk(total_size=0, count=2)
        with pytest.raises(ProtocolError, match="data_size=0"):
            ChunkAssembler(first, current_buffered=0, max_buffered_size=1024)

    def test_exceeds_max_message_size_raises(self):
        """Size exceeding MAX_PAYLOAD_SIZE should raise error."""
        first = make_first_chunk(total_size=MAX_PAYLOAD_SIZE + 1, count=2)
        with pytest.raises(ProtocolError, match="MAX_MESSAGE_SIZE"):
            ChunkAssembler(first, current_buffered=0, max_buffered_size=MAX_PAYLOAD_SIZE * 2)

    def test_exceeds_max_buffered_size_raises(self):
        """Pre-allocation exceeding max_buffered_size should raise error."""
        first = make_first_chunk(total_size=500, count=2)
        with pytest.raises(ProtocolError, match="MAX_BUFFERED_SIZE"):
            ChunkAssembler(first, current_buffered=600, max_buffered_size=1000)

    def test_exactly_at_max_buffered_size_ok(self):
        """Exactly at max_buffered_size should be accepted."""
        first = make_first_chunk(total_size=400, count=2)
        assembler = ChunkAssembler(first, current_buffered=600, max_buffered_size=1000)
        assert assembler.declared_size == 400

    def test_exactly_at_max_message_size_ok(self):
        """Exactly at MAX_PAYLOAD_SIZE should be accepted."""
        first = make_first_chunk(total_size=MAX_PAYLOAD_SIZE, count=2)
        assembler = ChunkAssembler(first, current_buffered=0, max_buffered_size=MAX_PAYLOAD_SIZE)
        assert assembler.declared_size == MAX_PAYLOAD_SIZE


class TestChunkAssemblerInOrder:
    """Tests for in-order chunk assembly (zero-copy path)."""

    def test_two_chunks_in_order(self):
        """Two chunks arriving in order should return original buffer."""
        body = b"hello world"
        first = make_first_chunk(total_size=len(body), count=2)
        assembler = ChunkAssembler(first, current_buffered=0, max_buffered_size=1024)
        internal_buffer = assembler._buffer

        done = assembler.add(make_body_chunk(index=1, payload=body))
        assert done is True

        result, meta = assembler.assemble()
        assert bytes(result) == body
        assert meta is first
        # Zero-copy: should return the same buffer
        assert result is internal_buffer

    def test_three_chunks_in_order(self):
        """Three chunks in order should concatenate correctly."""
        part_a = b"AAAA"
        part_b = b"BBBB"
        first = make_first_chunk(total_size=len(part_a) + len(part_b), count=3)
        assembler = ChunkAssembler(first, current_buffered=0, max_buffered_size=1024)
        internal_buffer = assembler._buffer

        assert assembler.add(make_body_chunk(index=1, payload=part_a, count=3)) is False
        assert assembler.add(make_body_chunk(index=2, payload=part_b, count=3)) is True

        result, _ = assembler.assemble()
        assert bytes(result) == part_a + part_b
        assert result is internal_buffer

    def test_add_returns_false_until_last(self):
        """add() should return False until the last chunk."""
        parts = [bytes([i] * 10) for i in range(1, 5)]
        total = sum(len(p) for p in parts)
        first = make_first_chunk(total_size=total, count=len(parts) + 1)
        assembler = ChunkAssembler(first, current_buffered=0, max_buffered_size=total + 100)

        for i, part in enumerate(parts, start=1):
            is_last = i == len(parts)
            assert assembler.add(make_body_chunk(index=i, payload=part, count=len(parts) + 1)) is is_last

        result, _ = assembler.assemble()
        assert bytes(result) == b"".join(parts)


class TestChunkAssemblerOutOfOrder:
    """Tests for out-of-order chunk assembly (copy path)."""

    def test_two_chunks_reversed(self):
        """Two chunks arriving in reverse order should still assemble correctly."""
        part_a = b"FIRST_PART_"
        part_b = b"SECOND_PART"
        first = make_first_chunk(total_size=len(part_a) + len(part_b), count=3)
        assembler = ChunkAssembler(first, current_buffered=0, max_buffered_size=1024)
        original_buffer = assembler._buffer

        # Arrive in reverse order: index 2 before index 1
        assert assembler.add(make_body_chunk(index=2, payload=part_b, count=3)) is False
        assert assembler.add(make_body_chunk(index=1, payload=part_a, count=3)) is True

        result, _ = assembler.assemble()
        assert bytes(result) == part_a + part_b
        # Out-of-order should produce a new buffer
        assert result is not original_buffer

    def test_three_chunks_permutation(self):
        """All non-identity permutations of 3 body chunks should work."""
        parts = [bytes([i] * 8) for i in range(1, 4)]
        expected = b"".join(parts)
        total = len(expected)

        for perm in itertools.permutations([1, 2, 3]):
            if perm == (1, 2, 3):
                continue  # in-order covered elsewhere
            first = make_first_chunk(total_size=total, count=4)
            assembler = ChunkAssembler(first, current_buffered=0, max_buffered_size=total + 100)
            for idx in perm:
                assembler.add(make_body_chunk(index=idx, payload=parts[idx - 1], count=4))
            result, _ = assembler.assemble()
            assert bytes(result) == expected, f"Failed for permutation {perm}"


class TestChunkAssemblerErrors:
    """Tests for error conditions in ChunkAssembler."""

    def test_duplicate_chunk_index_raises(self):
        """Duplicate chunk index should raise error."""
        first = make_first_chunk(total_size=20, count=3)
        assembler = ChunkAssembler(first, current_buffered=0, max_buffered_size=1024)
        assembler.add(make_body_chunk(index=1, payload=b"A" * 10, count=3))
        with pytest.raises(ProtocolError, match=r"[Dd]uplicate"):
            assembler.add(make_body_chunk(index=1, payload=b"B" * 5, count=3))

    def test_overflow_raises(self):
        """Payload exceeding declared size should raise error."""
        first = make_first_chunk(total_size=10, count=2)
        assembler = ChunkAssembler(first, current_buffered=0, max_buffered_size=1024)
        with pytest.raises(ProtocolError, match="exceed"):
            assembler.add(make_body_chunk(index=1, payload=b"X" * 11, count=2))

    def test_partial_overflow_raises(self):
        """Second chunk pushing past boundary should raise error."""
        first = make_first_chunk(total_size=10, count=3)
        assembler = ChunkAssembler(first, current_buffered=0, max_buffered_size=1024)
        assembler.add(make_body_chunk(index=1, payload=b"A" * 6, count=3))
        with pytest.raises(ProtocolError, match="exceed"):
            assembler.add(make_body_chunk(index=2, payload=b"B" * 5, count=3))

    def test_assemble_before_all_chunks_raises(self):
        """Calling assemble() before all chunks arrive should raise."""
        first = make_first_chunk(total_size=20, count=3)
        assembler = ChunkAssembler(first, current_buffered=0, max_buffered_size=1024)
        assembler.add(make_body_chunk(index=1, payload=b"A" * 10, count=3))
        with pytest.raises(AssertionError):
            assembler.assemble()

    def test_none_payload_raises(self):
        """Chunk with None payload should raise error."""
        first = make_first_chunk(total_size=10, count=2)
        assembler = ChunkAssembler(first, current_buffered=0, max_buffered_size=1024)
        chunk = Chunk(index=1, count=2, data_size=10, identifier=1, payload=None)
        with pytest.raises(ProtocolError):
            assembler.add(chunk)


class TestSplitSingleChunk:
    """Tests for split_payload with single-chunk outputs."""

    @pytest.mark.asyncio
    async def test_empty_payload(self):
        """Empty payload should produce one chunk with zero data_size."""
        chunks = await collect_chunks(ChunkAssembler.split_payload(memoryview(b"")))
        assert len(chunks) == 1
        assert chunks[0].index == 0
        assert chunks[0].count == 1
        assert chunks[0].data_size == 0
        assert len(chunks[0].payload) == 0

    @pytest.mark.asyncio
    async def test_single_source_zero_copy(self):
        """Single memoryview <= MAX_CHUNK_SIZE should use same buffer."""
        src = bytearray(b"the quick brown fox")
        mv = memoryview(src)
        chunks = await collect_chunks(ChunkAssembler.split_payload(mv))
        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.index == 0
        assert chunk.count == 1
        assert bytes(chunk.payload) == bytes(src)
        # Zero-copy: payload should share backing bytearray
        assert chunk.payload.obj is src

    @pytest.mark.asyncio
    async def test_multiple_sources_fit_in_one_chunk(self):
        """Multiple small sources should be concatenated into one chunk."""
        a = bytearray(b"hello ")
        b = bytearray(b"world")
        chunks = await collect_chunks(ChunkAssembler.split_payload(memoryview(a), memoryview(b)))
        assert len(chunks) == 1
        assert bytes(chunks[0].payload) == b"hello world"

    @pytest.mark.asyncio
    async def test_exactly_max_chunk_size(self):
        """Payload exactly at MAX_CHUNK_SIZE should be single chunk."""
        src = bytearray(MAX_CHUNK_SIZE)
        chunks = await collect_chunks(ChunkAssembler.split_payload(memoryview(src)))
        assert len(chunks) == 1
        assert chunks[0].data_size == MAX_CHUNK_SIZE
        assert chunks[0].payload.obj is src


class TestSplitMultiChunk:
    """Tests for split_payload with multi-chunk outputs."""

    @pytest.mark.asyncio
    async def test_two_chunks_exact_split(self):
        """Payload exactly 2x MAX_CHUNK_SIZE should produce 3 chunks."""
        total = MAX_CHUNK_SIZE * 2
        src = bytearray(list(range(256)) * (total // 256))
        chunks = await collect_chunks(ChunkAssembler.split_payload(memoryview(src)))

        # header-only + 2 body chunks
        assert len(chunks) == 3
        assert chunks[0].index == 0
        assert chunks[0].count == 3
        assert chunks[0].data_size == total
        assert len(chunks[0].payload) == 0

        assert chunks[1].index == 1
        assert chunks[1].data_size == MAX_CHUNK_SIZE
        assert chunks[2].index == 2
        assert chunks[2].data_size == MAX_CHUNK_SIZE

        # Reassemble and verify
        assembled = bytes(chunks[1].payload) + bytes(chunks[2].payload)
        assert assembled == bytes(src)

    @pytest.mark.asyncio
    async def test_three_chunks_partial_last(self):
        """Payload 2.5x MAX_CHUNK_SIZE should produce 4 chunks with partial last."""
        total = int(MAX_CHUNK_SIZE * 2.5)
        src = bytearray(b"\xab" * total)
        chunks = await collect_chunks(ChunkAssembler.split_payload(memoryview(src)))

        # header-only + 3 body chunks
        assert len(chunks) == 4
        body_chunks = chunks[1:]
        assembled = b"".join(bytes(c.payload) for c in body_chunks)
        assert assembled == bytes(src)

    @pytest.mark.asyncio
    async def test_large_payload_roundtrip(self):
        """Split then reassemble a large payload through ChunkAssembler."""
        total = MAX_CHUNK_SIZE * 3 + 12345
        src = bytearray(i % 251 for i in range(total))
        chunks = await collect_chunks(ChunkAssembler.split_payload(memoryview(src)))

        body_chunks = chunks[1:]
        first = chunks[0]

        assembler = ChunkAssembler(
            first,
            current_buffered=0,
            max_buffered_size=MAX_PAYLOAD_SIZE,
        )
        done = False
        for chunk in body_chunks:
            done = assembler.add(chunk)

        assert done is True
        result, _ = assembler.assemble()
        assert bytes(result) == bytes(src)

    @pytest.mark.asyncio
    async def test_zero_copy_body_chunks_single_source(self):
        """Body chunks from single large source should be sub-views."""
        total = MAX_CHUNK_SIZE * 2 + 1000
        src = bytearray(b"\xcc" * total)
        chunks = await collect_chunks(ChunkAssembler.split_payload(memoryview(src)))

        body_chunks = chunks[1:]
        for chunk in body_chunks:
            # Every body chunk should share backing bytearray with src
            assert chunk.payload.obj is src, (
                f"Chunk {chunk.index} payload not zero-copy"
            )

    @pytest.mark.asyncio
    async def test_boundary_chunk_allocates_new_buffer(self):
        """Chunk straddling source boundary should get new buffer."""
        half = MAX_CHUNK_SIZE // 2
        chunk_a = bytearray(b"\xaa" * (half + 1))
        chunk_b = bytearray(b"\xbb" * (MAX_CHUNK_SIZE - 1))

        chunks = await collect_chunks(
            ChunkAssembler.split_payload(memoryview(chunk_a), memoryview(chunk_b))
        )
        assert len(chunks) == 3  # header + 2 body

        body_chunks = chunks[1:]
        assembled = b"".join(bytes(c.payload) for c in body_chunks)
        assert assembled == bytes(chunk_a) + bytes(chunk_b)

        # First body chunk straddles the split - should not share either source
        boundary_chunk = body_chunks[0]
        assert boundary_chunk.payload.obj is not chunk_a
        assert boundary_chunk.payload.obj is not chunk_b

    @pytest.mark.asyncio
    async def test_exceeds_max_message_size_raises(self):
        """Payload exceeding MAX_PAYLOAD_SIZE should raise error."""
        oversized = bytearray(MAX_PAYLOAD_SIZE + 1)
        with pytest.raises(ProtocolError, match="MAX_MESSAGE_SIZE"):
            await collect_chunks(ChunkAssembler.split_payload(memoryview(oversized)))

    @pytest.mark.asyncio
    async def test_roundtrip_out_of_order_assembly(self):
        """Split then reassemble body chunks in reverse order."""
        total = MAX_CHUNK_SIZE * 2 + 7777
        src = bytearray(i % 199 for i in range(total))
        chunks = await collect_chunks(ChunkAssembler.split_payload(memoryview(src)))

        first_chunk = chunks[0]
        body_chunks = chunks[1:]

        assembler = ChunkAssembler(
            first_chunk,
            current_buffered=0,
            max_buffered_size=MAX_PAYLOAD_SIZE,
        )

        # Feed in reverse order
        done = False
        for chunk in reversed(body_chunks):
            done = assembler.add(chunk)

        assert done is True
        result, _ = assembler.assemble()
        assert bytes(result) == bytes(src)


class TestSplitMultipleSourceChunks:
    """Tests for split_payload with multiple source chunks."""

    @pytest.mark.asyncio
    async def test_many_small_sources(self):
        """Many small 1-byte sources spanning multiple chunks."""
        chunk_count = MAX_CHUNK_SIZE * 2 + 500
        sources = [memoryview(bytearray([i % 256])) for i in range(chunk_count)]
        chunks = await collect_chunks(ChunkAssembler.split_payload(*sources))

        body_chunks = chunks[1:]
        assembled = b"".join(bytes(c.payload) for c in body_chunks)
        assert len(assembled) == chunk_count
        assert assembled == bytes(i % 256 for i in range(chunk_count))

    @pytest.mark.asyncio
    async def test_two_halves_same_as_one_chunk(self):
        """Two half-size sources should produce one chunk."""
        half = MAX_CHUNK_SIZE // 2
        a = bytearray(b"\x01" * half)
        b = bytearray(b"\x02" * half)
        chunks = await collect_chunks(ChunkAssembler.split_payload(memoryview(a), memoryview(b)))
        # total == MAX_CHUNK_SIZE -> single chunk
        assert len(chunks) == 1
        assert bytes(chunks[0].payload) == bytes(a) + bytes(b)

    @pytest.mark.asyncio
    async def test_index_sequence_contiguous(self):
        """Chunk indices should be 0, 1, 2, ... for any payload size."""
        total = MAX_CHUNK_SIZE * 4 + 3
        src = bytearray(total)
        chunks = await collect_chunks(ChunkAssembler.split_payload(memoryview(src)))
        for expected_idx, chunk in enumerate(chunks):
            assert chunk.index == expected_idx

    @pytest.mark.asyncio
    async def test_count_consistent(self):
        """All chunks should have the same count value."""
        total = MAX_CHUNK_SIZE * 3 + 1
        src = bytearray(total)
        chunks = await collect_chunks(ChunkAssembler.split_payload(memoryview(src)))
        counts = {c.count for c in chunks}
        assert len(counts) == 1
        assert chunks[0].count == len(chunks)

    @pytest.mark.asyncio
    async def test_total_body_size_matches_declared(self):
        """Sum of body chunk data_sizes should equal first chunk's data_size."""
        total = MAX_CHUNK_SIZE * 2 + 987
        src = bytearray(total)
        chunks = await collect_chunks(ChunkAssembler.split_payload(memoryview(src)))
        declared = chunks[0].data_size
        body_total = sum(c.data_size for c in chunks[1:])
        assert body_total == declared
        assert declared == total
