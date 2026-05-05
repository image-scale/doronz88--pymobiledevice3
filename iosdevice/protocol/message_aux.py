"""Message auxiliary argument encoding and decoding.

This module handles encoding and decoding of auxiliary arguments in DTX
messages. Arguments are serialized into a primitive dictionary wire format
where positional arguments use NULL as their key.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from bpylist2 import archiver

from .primitives import (
    NULL,
    WireBase,
    WireBuffer,
    WireDict,
    read_primitive,
)


logger = logging.getLogger(__name__)


class AuxData:
    """Encoder/decoder for DTX auxiliary argument lists.

    Auxiliary arguments are encoded as a primitive dictionary where
    each positional argument has NULL as its key. Complex objects
    are serialized using NSKeyedArchive into WireBuffer values.
    """

    @staticmethod
    def parse(data: bytes | bytearray | memoryview) -> list[Any]:
        """Parse auxiliary arguments from wire format.

        Args:
            data: Raw bytes containing encoded aux arguments.

        Returns:
            List of decoded argument values.

        Raises:
            ValueError: If the data format is invalid.
        """
        if len(data) == 0:
            return []

        stream = io.BytesIO(bytes(data))
        primitive_dict = read_primitive(stream)

        if not isinstance(primitive_dict, dict):
            raise ValueError(
                f"Expected dictionary for aux data, got {type(primitive_dict).__name__}"
            )

        if len(primitive_dict) != 1 or NULL not in primitive_dict:
            raise ValueError(
                f"Expected dictionary with single NULL key, got keys: {list(primitive_dict.keys())}"
            )

        values_list = primitive_dict[NULL]
        if not isinstance(values_list, list):
            raise ValueError(
                f"Expected list for NULL key value, got {type(values_list).__name__}"
            )

        result = []
        for item in values_list:
            if item is NULL:
                logger.warning("Received NULL argument instead of empty buffer")
                result.append(None)
            elif isinstance(item, WireBuffer):
                if len(item) == 0:
                    result.append(None)
                else:
                    try:
                        result.append(archiver.unarchive(item))
                    except Exception as e:
                        raise ValueError(f"Failed to unarchive buffer: {e}") from e
            elif isinstance(item, WireBase):
                # Primitive types (int, float, string) pass through directly
                result.append(item)
            else:
                # Already decoded value
                result.append(item)

        return result

    @staticmethod
    def build(args: list[Any] | tuple[Any, ...] | None) -> bytes:
        """Encode argument list into wire format.

        Args:
            args: List of arguments to encode.

        Returns:
            Encoded bytes, or empty bytes if no arguments.

        Raises:
            ValueError: If encoding fails.
        """
        if not args:
            return b""

        encoded_args = []
        for arg in args:
            if isinstance(arg, WireBase):
                # Already a wire type - use directly
                encoded_args.append(arg)
            elif arg is None:
                # None becomes empty buffer
                encoded_args.append(WireBuffer(b""))
            else:
                # Archive complex objects
                try:
                    archived = archiver.archive(arg)
                    encoded_args.append(WireBuffer(archived))
                except Exception as e:
                    raise ValueError(
                        f"Failed to archive argument {arg!r} of type {type(arg).__name__}: {e}"
                    ) from e

        # Wrap in primitive dictionary with NULL key
        pdict = WireDict({NULL: encoded_args})

        stream = io.BytesIO()
        pdict.write(stream)
        return stream.getvalue()
