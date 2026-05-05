"""DTX primitive value types for auxiliary argument encoding.

Primitive types are the wire-level representations used in DTX auxiliary
arguments. Each call-site value is encoded as one of these types:

- WireNull (type 10): Positional NULL marker (no value bytes)
- WireString (type 1): Length-prefixed UTF-8 string
- WireBuffer (type 2): Length-prefixed raw bytes or NSKeyedArchive blob
- WireInt32 (type 3): 32-bit signed integer
- WireInt64 (type 6): 64-bit signed integer
- WireFloat (type 9): IEEE-754 double
- WireDict (type 0xF0): Key-value dictionary

Each type inherits from both the wire base class and a Python builtin,
allowing transparent use in application code while preserving encoding intent.
"""

from __future__ import annotations

import io
import logging
import struct
from typing import Any, ClassVar


logger = logging.getLogger(__name__)

# Type mask - upper bits may carry optional flags
TYPE_MASK = 0xFF


class WireBase:
    """Base class for wire-level primitive types.

    Subclasses inherit from both WireBase and a Python builtin
    so they can be used transparently while carrying wire encoding intent.
    """

    type_code: ClassVar[int]

    @classmethod
    def read(cls, stream: io.BytesIO) -> "WireBase":
        """Parse this value from the stream. Called after type code is read."""
        raise NotImplementedError

    def write(self, stream: io.BytesIO) -> None:
        """Write the encoded value to stream (including type tag)."""
        raise NotImplementedError


class WireNull(WireBase):
    """NULL marker (type code 10). Used as positional slot marker.

    DTX aux dictionaries use NULL as the key for every positional argument.
    """

    type_code = 10
    _instance = None

    def __new__(cls):
        """Singleton pattern - all WireNull instances are the same."""
        if cls._instance is None:
            cls._instance = object.__new__(cls)
        return cls._instance

    @classmethod
    def read(cls, stream: io.BytesIO) -> "WireNull":
        """NULL has no value bytes - just return the singleton."""
        return NULL

    def write(self, stream: io.BytesIO) -> None:
        """Write just the type code, no value bytes."""
        stream.write(struct.pack("<I", self.type_code))

    def __eq__(self, other):
        return isinstance(other, WireNull)

    def __hash__(self):
        return hash(WireNull)

    def __repr__(self):
        return "NULL"


# Singleton instance
NULL = WireNull()


class WireString(WireBase, str):
    """Length-prefixed UTF-8 string (type code 1)."""

    type_code = 1

    @classmethod
    def read(cls, stream: io.BytesIO) -> "WireString":
        """Read length-prefixed UTF-8 string."""
        length = struct.unpack("<I", stream.read(4))[0]
        data = stream.read(length)
        return cls(data.decode("utf-8", errors="replace"))

    def write(self, stream: io.BytesIO) -> None:
        """Write type code, length, and UTF-8 bytes."""
        encoded = str(self).encode("utf-8")
        stream.write(struct.pack("<II", self.type_code, len(encoded)))
        stream.write(encoded)


class WireBuffer(WireBase, bytes):
    """Raw bytes buffer (type code 2). May contain NSKeyedArchive data."""

    type_code = 2

    @classmethod
    def read(cls, stream: io.BytesIO) -> "WireBuffer":
        """Read length-prefixed bytes."""
        length = struct.unpack("<I", stream.read(4))[0]
        return cls(stream.read(length))

    def write(self, stream: io.BytesIO) -> None:
        """Write type code, length, and raw bytes."""
        stream.write(struct.pack("<II", self.type_code, len(self)))
        stream.write(bytes(self))


class WireInt32(WireBase, int):
    """32-bit signed integer (type code 3)."""

    type_code = 3

    @classmethod
    def read(cls, stream: io.BytesIO) -> "WireInt32":
        """Read 32-bit signed integer."""
        value = struct.unpack("<i", stream.read(4))[0]
        return cls(value)

    def write(self, stream: io.BytesIO) -> None:
        """Write type code and 32-bit value."""
        stream.write(struct.pack("<Ii", self.type_code, int(self)))


class WireInt64(WireBase, int):
    """64-bit signed integer (type code 6)."""

    type_code = 6

    @classmethod
    def read(cls, stream: io.BytesIO) -> "WireInt64":
        """Read 64-bit signed integer."""
        value = struct.unpack("<q", stream.read(8))[0]
        return cls(value)

    def write(self, stream: io.BytesIO) -> None:
        """Write type code and 64-bit value."""
        stream.write(struct.pack("<Iq", self.type_code, int(self)))


class WireFloat(WireBase, float):
    """IEEE-754 double (type code 9)."""

    type_code = 9

    @classmethod
    def read(cls, stream: io.BytesIO) -> "WireFloat":
        """Read 64-bit IEEE-754 double."""
        value = struct.unpack("<d", stream.read(8))[0]
        return cls(value)

    def write(self, stream: io.BytesIO) -> None:
        """Write type code and 64-bit double."""
        stream.write(struct.pack("<Id", self.type_code, float(self)))


class WireDict(WireBase, dict):
    """Primitive dictionary (type code 0xF0).

    Wire layout:
        u32  type_and_flags    0xF0 | optional flags in upper bits
        u32  reserved          always 0
        u64  body_length       byte count of key-value pairs
        [key_primitive, value_primitive] x N entries
    """

    type_code = 0xF0
    DEFAULT_MAGIC = 0x1F0  # Common observed value: 0x100 | 0xF0

    @classmethod
    def read(cls, stream: io.BytesIO) -> dict[Any, list[Any]]:
        """Read primitive dictionary from stream."""
        reserved = struct.unpack("<I", stream.read(4))[0]
        body_length = struct.unpack("<Q", stream.read(8))[0]

        start_pos = stream.tell()
        result: dict[Any, list[Any]] = {}

        while stream.tell() - start_pos < body_length:
            key = read_primitive(stream)
            value = read_primitive(stream)
            result.setdefault(key, []).append(value)

        if reserved != 0:
            logger.warning(f"WireDict: non-zero reserved field {reserved:#x}")

        return result

    def write(self, stream: io.BytesIO) -> None:
        """Write primitive dictionary to stream."""
        # Write to temp buffer to get body length
        body = io.BytesIO()
        for key, values in self.items():
            if not isinstance(values, list):
                raise ValueError(f"WireDict values must be lists, got {type(values)}")
            for value in values:
                write_primitive(key, body)
                write_primitive(value, body)

        body_bytes = body.getvalue()

        # Write header + body
        stream.write(struct.pack("<IIQ", self.DEFAULT_MAGIC, 0, len(body_bytes)))
        stream.write(body_bytes)


# Type registry: type code -> class
TYPE_REGISTRY: dict[int, type[WireBase]] = {
    WireNull.type_code: WireNull,
    WireString.type_code: WireString,
    WireBuffer.type_code: WireBuffer,
    WireInt32.type_code: WireInt32,
    WireInt64.type_code: WireInt64,
    WireFloat.type_code: WireFloat,
    WireDict.type_code: WireDict,
}


def read_primitive(stream: io.BytesIO) -> Any:
    """Read a single primitive value from stream."""
    raw_type = struct.unpack("<I", stream.read(4))[0]
    type_code = raw_type & TYPE_MASK

    cls = TYPE_REGISTRY.get(type_code)
    if cls is None:
        raise ValueError(f"Unknown primitive type code {raw_type:#x}")

    return cls.read(stream)


def write_primitive(value: Any, stream: io.BytesIO) -> None:
    """Write a primitive value to stream."""
    if not isinstance(value, WireBase):
        raise ValueError(f"Expected WireBase instance, got {type(value)}")
    value.write(stream)
