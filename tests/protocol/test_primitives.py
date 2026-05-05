"""Tests for DTX primitive types and auxiliary argument encoding."""

import io
import struct

import pytest
from bpylist2 import archiver

from iosdevice.protocol.primitives import (
    NULL,
    WireNull,
    WireString,
    WireBuffer,
    WireInt32,
    WireInt64,
    WireFloat,
    WireDict,
    WireBase,
    TYPE_REGISTRY,
    read_primitive,
    write_primitive,
)
from iosdevice.protocol.message_aux import AuxData


class TestWireNull:
    """Tests for WireNull primitive."""

    def test_singleton(self):
        """All WireNull instances should be the same."""
        null1 = WireNull()
        null2 = WireNull()
        assert null1 is null2
        assert null1 is NULL

    def test_type_code(self):
        """Type code should be 10."""
        assert WireNull.type_code == 10

    def test_roundtrip(self):
        """WireNull should survive write/read cycle."""
        stream = io.BytesIO()
        NULL.write(stream)

        stream.seek(0)
        # Read type code
        type_code = struct.unpack("<I", stream.read(4))[0]
        assert type_code == 10

        # Read should return the singleton
        result = WireNull.read(stream)
        assert result is NULL

    def test_equality(self):
        """WireNull instances should be equal."""
        assert NULL == WireNull()
        assert not (NULL == "null")
        assert not (NULL == None)

    def test_hash(self):
        """WireNull should be hashable."""
        d = {NULL: "value"}
        assert d[WireNull()] == "value"

    def test_repr(self):
        """repr should be 'NULL'."""
        assert repr(NULL) == "NULL"


class TestWireString:
    """Tests for WireString primitive."""

    def test_type_code(self):
        """Type code should be 1."""
        assert WireString.type_code == 1

    def test_basic_roundtrip(self):
        """Basic string should survive write/read cycle."""
        original = WireString("hello world")
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        type_code = struct.unpack("<I", stream.read(4))[0]
        assert type_code == 1

        result = WireString.read(stream)
        assert result == "hello world"
        assert isinstance(result, WireString)

    def test_empty_string(self):
        """Empty string should work."""
        original = WireString("")
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireString.read(stream)
        assert result == ""

    def test_unicode(self):
        """Unicode characters should be preserved."""
        original = WireString("日本語テスト 🎉")
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireString.read(stream)
        assert result == "日本語テスト 🎉"

    def test_string_behavior(self):
        """WireString should behave like str."""
        ws = WireString("test")
        assert ws.upper() == "TEST"
        assert ws + " suffix" == "test suffix"
        assert len(ws) == 4


class TestWireBuffer:
    """Tests for WireBuffer primitive."""

    def test_type_code(self):
        """Type code should be 2."""
        assert WireBuffer.type_code == 2

    def test_basic_roundtrip(self):
        """Basic bytes should survive write/read cycle."""
        original = WireBuffer(b"\x00\x01\x02\xff")
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        type_code = struct.unpack("<I", stream.read(4))[0]
        assert type_code == 2

        result = WireBuffer.read(stream)
        assert result == b"\x00\x01\x02\xff"
        assert isinstance(result, WireBuffer)

    def test_empty_buffer(self):
        """Empty buffer should work."""
        original = WireBuffer(b"")
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireBuffer.read(stream)
        assert result == b""

    def test_large_buffer(self):
        """Large buffer should work."""
        data = bytes(range(256)) * 100
        original = WireBuffer(data)
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireBuffer.read(stream)
        assert result == data

    def test_bytes_behavior(self):
        """WireBuffer should behave like bytes."""
        wb = WireBuffer(b"test")
        assert wb.hex() == "74657374"
        assert len(wb) == 4


class TestWireInt32:
    """Tests for WireInt32 primitive."""

    def test_type_code(self):
        """Type code should be 3."""
        assert WireInt32.type_code == 3

    def test_positive_roundtrip(self):
        """Positive int32 should survive write/read cycle."""
        original = WireInt32(12345)
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        type_code = struct.unpack("<I", stream.read(4))[0]
        assert type_code == 3

        result = WireInt32.read(stream)
        assert result == 12345
        assert isinstance(result, WireInt32)

    def test_negative_roundtrip(self):
        """Negative int32 should survive write/read cycle."""
        original = WireInt32(-12345)
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireInt32.read(stream)
        assert result == -12345

    def test_zero(self):
        """Zero should work."""
        original = WireInt32(0)
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireInt32.read(stream)
        assert result == 0

    def test_max_value(self):
        """Maximum int32 should work."""
        original = WireInt32(2147483647)
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireInt32.read(stream)
        assert result == 2147483647

    def test_min_value(self):
        """Minimum int32 should work."""
        original = WireInt32(-2147483648)
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireInt32.read(stream)
        assert result == -2147483648

    def test_int_behavior(self):
        """WireInt32 should behave like int."""
        wi = WireInt32(10)
        assert wi + 5 == 15
        assert wi * 2 == 20


class TestWireInt64:
    """Tests for WireInt64 primitive."""

    def test_type_code(self):
        """Type code should be 6."""
        assert WireInt64.type_code == 6

    def test_large_positive(self):
        """Large positive int64 should work."""
        original = WireInt64(9223372036854775807)
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        type_code = struct.unpack("<I", stream.read(4))[0]
        assert type_code == 6

        result = WireInt64.read(stream)
        assert result == 9223372036854775807

    def test_large_negative(self):
        """Large negative int64 should work."""
        original = WireInt64(-9223372036854775808)
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireInt64.read(stream)
        assert result == -9223372036854775808


class TestWireFloat:
    """Tests for WireFloat primitive."""

    def test_type_code(self):
        """Type code should be 9."""
        assert WireFloat.type_code == 9

    def test_basic_roundtrip(self):
        """Basic float should survive write/read cycle."""
        original = WireFloat(3.14159)
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        type_code = struct.unpack("<I", stream.read(4))[0]
        assert type_code == 9

        result = WireFloat.read(stream)
        assert abs(result - 3.14159) < 1e-10

    def test_negative(self):
        """Negative float should work."""
        original = WireFloat(-273.15)
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireFloat.read(stream)
        assert abs(result - (-273.15)) < 1e-10

    def test_zero(self):
        """Zero should work."""
        original = WireFloat(0.0)
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireFloat.read(stream)
        assert result == 0.0

    def test_float_behavior(self):
        """WireFloat should behave like float."""
        wf = WireFloat(2.5)
        assert wf + 0.5 == 3.0
        assert wf * 2 == 5.0


class TestWireDict:
    """Tests for WireDict primitive."""

    def test_type_code(self):
        """Type code should be 0xF0."""
        assert WireDict.type_code == 0xF0

    def test_basic_roundtrip(self):
        """Basic dictionary should survive write/read cycle."""
        original = WireDict({
            NULL: [WireInt32(42)],
        })
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        # Read header manually
        type_and_flags = struct.unpack("<I", stream.read(4))[0]
        assert type_and_flags & 0xFF == 0xF0

        result = WireDict.read(stream)
        assert NULL in result
        assert len(result[NULL]) == 1
        assert result[NULL][0] == 42

    def test_multiple_values(self):
        """Multiple values for same key should work."""
        original = WireDict({
            NULL: [WireInt32(1), WireInt32(2), WireInt32(3)],
        })
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireDict.read(stream)

        assert result[NULL] == [1, 2, 3]

    def test_mixed_types(self):
        """Mixed value types should work."""
        original = WireDict({
            NULL: [
                WireInt32(42),
                WireString("test"),
                WireFloat(3.14),
            ],
        })
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireDict.read(stream)

        assert result[NULL][0] == 42
        assert result[NULL][1] == "test"
        assert abs(result[NULL][2] - 3.14) < 0.01

    def test_empty_dict(self):
        """Empty dictionary should work."""
        original = WireDict({})
        stream = io.BytesIO()
        original.write(stream)

        stream.seek(0)
        struct.unpack("<I", stream.read(4))[0]  # skip type
        result = WireDict.read(stream)

        assert result == {}


class TestReadWritePrimitive:
    """Tests for read_primitive and write_primitive functions."""

    def test_read_all_types(self):
        """All type codes should be recognized."""
        assert 10 in TYPE_REGISTRY  # NULL
        assert 1 in TYPE_REGISTRY   # String
        assert 2 in TYPE_REGISTRY   # Buffer
        assert 3 in TYPE_REGISTRY   # Int32
        assert 6 in TYPE_REGISTRY   # Int64
        assert 9 in TYPE_REGISTRY   # Float
        assert 0xF0 in TYPE_REGISTRY  # Dict

    def test_unknown_type_raises(self):
        """Unknown type code should raise ValueError."""
        stream = io.BytesIO(struct.pack("<I", 0xFF))  # Invalid type
        with pytest.raises(ValueError, match="Unknown primitive type"):
            read_primitive(stream)

    def test_write_non_wirebase_raises(self):
        """Writing non-WireBase should raise ValueError."""
        stream = io.BytesIO()
        with pytest.raises(ValueError, match="Expected WireBase"):
            write_primitive("not a wire type", stream)


class TestAuxDataParse:
    """Tests for AuxData.parse()."""

    def test_empty_data(self):
        """Empty data should return empty list."""
        result = AuxData.parse(b"")
        assert result == []

    def test_single_int_argument(self):
        """Single integer argument should parse correctly."""
        # Build aux data with one int
        aux_bytes = AuxData.build([WireInt32(42)])
        result = AuxData.parse(aux_bytes)
        assert len(result) == 1
        assert result[0] == 42

    def test_multiple_arguments(self):
        """Multiple arguments should parse correctly."""
        aux_bytes = AuxData.build([
            WireInt32(1),
            WireString("hello"),
            WireFloat(3.14),
        ])
        result = AuxData.parse(aux_bytes)
        assert len(result) == 3
        assert result[0] == 1
        assert result[1] == "hello"
        assert abs(result[2] - 3.14) < 0.01

    def test_empty_buffer_becomes_none(self):
        """Empty buffer should become None."""
        aux_bytes = AuxData.build([None])
        result = AuxData.parse(aux_bytes)
        assert result == [None]

    def test_archived_object(self):
        """Archived object should be unarchived."""
        original = {"key": "value", "number": 42}
        aux_bytes = AuxData.build([original])
        result = AuxData.parse(aux_bytes)
        assert len(result) == 1
        assert result[0] == original


class TestAuxDataBuild:
    """Tests for AuxData.build()."""

    def test_empty_list(self):
        """Empty list should return empty bytes."""
        result = AuxData.build([])
        assert result == b""

    def test_none_list(self):
        """None should return empty bytes."""
        result = AuxData.build(None)
        assert result == b""

    def test_wire_types_pass_through(self):
        """WireBase types should be used directly."""
        aux_bytes = AuxData.build([WireInt32(42)])
        # Should successfully build
        assert len(aux_bytes) > 0

    def test_none_becomes_empty_buffer(self):
        """None argument should become empty buffer."""
        aux_bytes = AuxData.build([None])
        result = AuxData.parse(aux_bytes)
        assert result == [None]

    def test_complex_object_archived(self):
        """Complex object should be archived."""
        obj = {"nested": {"list": [1, 2, 3]}}
        aux_bytes = AuxData.build([obj])
        result = AuxData.parse(aux_bytes)
        assert result[0] == obj


class TestAuxDataRoundtrip:
    """Roundtrip tests for AuxData."""

    def test_mixed_types_roundtrip(self):
        """Mixed primitive and complex types should roundtrip."""
        args = [
            WireInt32(100),
            WireString("test string"),
            WireFloat(-999.5),
            {"dict": "value"},
            None,
        ]
        aux_bytes = AuxData.build(args)
        result = AuxData.parse(aux_bytes)

        assert result[0] == 100
        assert result[1] == "test string"
        assert abs(result[2] - (-999.5)) < 0.01
        assert result[3] == {"dict": "value"}
        assert result[4] is None

    def test_many_arguments(self):
        """Many arguments should roundtrip."""
        args = [WireInt32(i) for i in range(50)]
        aux_bytes = AuxData.build(args)
        result = AuxData.parse(aux_bytes)

        assert len(result) == 50
        for i, val in enumerate(result):
            assert val == i

    def test_tuple_input(self):
        """Tuple input should work same as list."""
        args = (WireInt32(1), WireInt32(2))
        aux_bytes = AuxData.build(args)
        result = AuxData.parse(aux_bytes)
        assert result == [1, 2]
