"""NS (NextStep/Objective-C) type wrappers for NSKeyedArchive serialization.

These classes allow Python to encode and decode Objective-C types used in
DTX message payloads and auxiliary arguments. They integrate with bpylist2
for automatic NSKeyedArchive serialization.
"""

from __future__ import annotations

import datetime
import os
import uuid
from typing import Any, Optional

from bpylist2 import archiver


class TapMessage:
    """Proxy for DTTapMessage subclasses from device diagnostics tap.

    These messages contain embedded plist data that is extracted during decode.
    """

    @staticmethod
    def decode_archive(archive_obj) -> Any:
        """Extract the embedded plist from a tap message."""
        return archive_obj.decode("DTTapMessagePlist")


class Null:
    """Proxy for Objective-C NSNull - represents a typed null value."""

    @staticmethod
    def decode_archive(archive_obj) -> None:
        """NSNull always decodes to Python None."""
        return None


class Error:
    """Represents an NSError from the remote device.

    NSErrors contain an error code, domain string, and optional user info
    dictionary with additional details like localized descriptions.
    """

    def __init__(self, code: int, domain: str, user_info: Optional[dict] = None):
        self.code: int = code
        self.domain: str = domain
        self.user_info: Optional[dict] = user_info

    def encode_archive(self, archive_obj: archiver.ArchivingObject) -> None:
        """Encode this error into an NSKeyedArchive object."""
        archive_obj.encode("NSDomain", self.domain)
        archive_obj.encode("NSCode", self.code)
        archive_obj.encode("NSUserInfo", self.user_info)

    @staticmethod
    def decode_archive(archive_obj) -> "Error":
        """Decode an NSKeyedArchive NSError into an Error instance."""
        domain = archive_obj.decode("NSDomain")
        code = archive_obj.decode("NSCode")
        user_info = archive_obj.decode("NSUserInfo")
        assert (
            (user_info is None or isinstance(user_info, dict))
            and isinstance(domain, str)
            and isinstance(code, int)
        ), f"Invalid NSError archive: domain={domain!r} code={code!r} user_info={user_info!r}"
        return Error(code, domain, user_info)

    @staticmethod
    def unrecognized_selector(selector: str) -> "Error":
        """Create an error for an unrecognized selector."""
        return Error(
            1,
            "DTXMessage",
            {"NSLocalizedDescription": f"Unable to invoke {selector!r} - it does not respond to the selector"},
        )

    @staticmethod
    def from_exception(selector: str, exc: Exception) -> "Error":
        """Create an error wrapping an exception from selector dispatch."""
        return Error(
            1,
            "DTXMessage",
            {"NSLocalizedDescription": f"In invocation of method {selector!r}: {exc!r}"},
        )


class UniqueID(uuid.UUID):
    """Proxy for NSUUID - extends Python's UUID class with NSKeyedArchive support."""

    @staticmethod
    def random() -> "UniqueID":
        """Generate a random version-4 UUID."""
        return UniqueID(bytes=os.urandom(16))

    def encode_archive(self, archive_obj: archiver.ArchivingObject) -> None:
        """Encode this UUID into an NSKeyedArchive object."""
        archive_obj.encode("NS.uuidbytes", self.bytes)

    @staticmethod
    def decode_archive(archive_obj: archiver.ArchivedObject) -> "UniqueID":
        """Decode an NSKeyedArchive NSUUID into a UniqueID instance."""
        return UniqueID(bytes=archive_obj.decode("NS.uuidbytes"))


class URL:
    """Proxy for NSURL - stores base and relative URL components."""

    def __init__(self, base, relative):
        self.base = base
        self.relative = relative

    def encode_archive(self, archive_obj: archiver.ArchivingObject) -> None:
        """Encode this URL into an NSKeyedArchive object."""
        archive_obj.encode("NS.base", self.base)
        archive_obj.encode("NS.relative", self.relative)

    @staticmethod
    def decode_archive(archive_obj: archiver.ArchivedObject) -> "URL":
        """Decode an NSKeyedArchive NSURL into a URL instance."""
        return URL(archive_obj.decode("NS.base"), archive_obj.decode("NS.relative"))


class Value:
    """Proxy for NSValue - extracts the embedded rect value."""

    @staticmethod
    def decode_archive(archive_obj: archiver.ArchivedObject) -> Any:
        """Decode the underlying NSValue data (typically a rect)."""
        return archive_obj.decode("NS.rectval")


class MutableData:
    """Proxy for NSMutableData - extracts raw bytes."""

    @staticmethod
    def decode_archive(archive_obj: archiver.ArchivedObject) -> bytes:
        """Decode the underlying bytes data."""
        return archive_obj.decode("NS.data")


class MutableString:
    """Proxy for NSMutableString - extracts the string value."""

    @staticmethod
    def decode_archive(archive_obj: archiver.ArchivedObject) -> str:
        """Decode the underlying string value."""
        return archive_obj.decode("NS.string")


class Date:
    """Proxy for NSDate - stores timestamp relative to Cocoa epoch.

    The Cocoa epoch is 2001-01-01 00:00:00 UTC. This class stores the
    raw timestamp and provides conversion to Python datetime.
    """

    # 2001-01-01T00:00:00 UTC as Unix timestamp
    COCOA_EPOCH_UNIX: float = 978307200.0

    def __init__(self, timestamp: float):
        """Initialize with seconds since Cocoa epoch."""
        self.timestamp: float = timestamp

    @property
    def utc(self) -> datetime.datetime:
        """Return the date as a UTC datetime object."""
        return datetime.datetime.fromtimestamp(
            self.timestamp + self.COCOA_EPOCH_UNIX,
            tz=datetime.timezone.utc
        )

    def __repr__(self) -> str:
        return f"Date({self.utc.isoformat()})"

    @staticmethod
    def decode_archive(archive_obj: archiver.ArchivedObject) -> "Date":
        """Decode an NSKeyedArchive NSDate into a Date instance."""
        t = archive_obj.decode("NS.time")
        return Date(float(t) if t is not None else 0.0)


# Register all NS types with the bpylist2 archiver
archiver.update_class_map({
    "DTSysmonTapMessage": TapMessage,
    "DTTapHeartbeatMessage": TapMessage,
    "DTTapStatusMessage": TapMessage,
    "DTKTraceTapMessage": TapMessage,
    "DTActivityTraceTapMessage": TapMessage,
    "DTTapMessage": TapMessage,
    "NSNull": Null,
    "NSError": Error,
    "NSUUID": UniqueID,
    "NSURL": URL,
    "NSValue": Value,
    "NSMutableData": MutableData,
    "NSMutableString": MutableString,
    "NSDate": Date,
})

# Allow bytes to be inlined in archives
archiver.Archive.inline_types = list({*archiver.Archive.inline_types, bytes})
