"""Tests for NS type wrappers and NSKeyedArchive integration."""

import datetime

import pytest
from bpylist2 import archiver

from iosdevice.protocol.ns_types import (
    Error,
    UniqueID,
    Null,
    URL,
    Value,
    MutableData,
    MutableString,
    Date,
    TapMessage,
)
from iosdevice.protocol.constants import MessageType


class TestMessageType:
    """Tests for MessageType enumeration."""

    def test_ok_value(self):
        """OK should be 0."""
        assert MessageType.OK == 0

    def test_data_value(self):
        """DATA should be 1."""
        assert MessageType.DATA == 1

    def test_dispatch_value(self):
        """DISPATCH should be 2."""
        assert MessageType.DISPATCH == 2

    def test_object_value(self):
        """OBJECT should be 3."""
        assert MessageType.OBJECT == 3

    def test_error_value(self):
        """ERROR should be 4."""
        assert MessageType.ERROR == 4

    def test_barrier_value(self):
        """BARRIER should be 5."""
        assert MessageType.BARRIER == 5

    def test_message_type_name(self):
        """Message type names should be accessible."""
        assert MessageType.DISPATCH.name == "DISPATCH"
        assert MessageType(3).name == "OBJECT"


class TestError:
    """Tests for NSError wrapper."""

    def test_basic_construction(self):
        """Error should store code, domain, and user_info."""
        error = Error(42, "TestDomain", {"key": "value"})
        assert error.code == 42
        assert error.domain == "TestDomain"
        assert error.user_info == {"key": "value"}

    def test_none_user_info(self):
        """Error should accept None user_info."""
        error = Error(1, "Domain")
        assert error.code == 1
        assert error.domain == "Domain"
        assert error.user_info is None

    def test_roundtrip_through_archive(self):
        """Error should survive NSKeyedArchive encode/decode."""
        original = Error(123, "MyDomain", {"NSLocalizedDescription": "Test error"})
        archived = archiver.archive(original)
        restored = archiver.unarchive(archived)

        assert isinstance(restored, Error)
        assert restored.code == 123
        assert restored.domain == "MyDomain"
        assert restored.user_info == {"NSLocalizedDescription": "Test error"}

    def test_roundtrip_minimal(self):
        """Error without user_info should roundtrip correctly."""
        original = Error(0, "EmptyDomain", None)
        archived = archiver.archive(original)
        restored = archiver.unarchive(archived)

        assert isinstance(restored, Error)
        assert restored.code == 0
        assert restored.domain == "EmptyDomain"
        assert restored.user_info is None

    def test_unrecognized_selector_factory(self):
        """unrecognized_selector should create appropriate error."""
        error = Error.unrecognized_selector("doSomething:")
        assert error.code == 1
        assert error.domain == "DTXMessage"
        assert "doSomething:" in error.user_info["NSLocalizedDescription"]
        assert "does not respond" in error.user_info["NSLocalizedDescription"]

    def test_from_exception_factory(self):
        """from_exception should wrap exception in error."""
        exc = ValueError("test failure")
        error = Error.from_exception("handleRequest:", exc)
        assert error.code == 1
        assert error.domain == "DTXMessage"
        assert "handleRequest:" in error.user_info["NSLocalizedDescription"]
        assert "ValueError" in error.user_info["NSLocalizedDescription"]


class TestUniqueID:
    """Tests for NSUUID wrapper."""

    def test_random_generates_uuid(self):
        """random() should generate valid UUIDs."""
        uid = UniqueID.random()
        assert len(uid.bytes) == 16
        # Should be a valid UUID string
        assert len(str(uid)) == 36  # UUID format: 8-4-4-4-12

    def test_random_generates_different_uuids(self):
        """random() should generate different UUIDs each time."""
        uid1 = UniqueID.random()
        uid2 = UniqueID.random()
        assert uid1 != uid2

    def test_from_bytes(self):
        """UniqueID should initialize from bytes."""
        data = b"\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99\xaa\xbb\xcc\xdd\xee\xff"
        uid = UniqueID(bytes=data)
        assert uid.bytes == data

    def test_roundtrip_through_archive(self):
        """UniqueID should survive NSKeyedArchive encode/decode."""
        original = UniqueID.random()
        archived = archiver.archive(original)
        restored = archiver.unarchive(archived)

        assert isinstance(restored, UniqueID)
        assert restored == original
        assert restored.bytes == original.bytes


class TestURL:
    """Tests for NSURL wrapper."""

    def test_basic_construction(self):
        """URL should store base and relative components."""
        url = URL("https://example.com", "/path/to/resource")
        assert url.base == "https://example.com"
        assert url.relative == "/path/to/resource"

    def test_none_components(self):
        """URL should accept None for base or relative."""
        url = URL(None, "relative/path")
        assert url.base is None
        assert url.relative == "relative/path"

    def test_roundtrip_through_archive(self):
        """URL should survive NSKeyedArchive encode/decode."""
        original = URL("https://base.com", "/relative")
        archived = archiver.archive(original)
        restored = archiver.unarchive(archived)

        assert isinstance(restored, URL)
        assert restored.base == "https://base.com"
        assert restored.relative == "/relative"


class TestDate:
    """Tests for NSDate wrapper."""

    def test_basic_construction(self):
        """Date should store timestamp."""
        date = Date(0.0)
        assert date.timestamp == 0.0

    def test_cocoa_epoch(self):
        """Timestamp 0 should correspond to 2001-01-01 00:00:00 UTC."""
        date = Date(0.0)
        utc = date.utc
        assert utc.year == 2001
        assert utc.month == 1
        assert utc.day == 1
        assert utc.hour == 0
        assert utc.minute == 0
        assert utc.second == 0
        assert utc.tzinfo == datetime.timezone.utc

    def test_positive_timestamp(self):
        """Positive timestamp should be after 2001-01-01."""
        # One day after epoch
        date = Date(86400.0)
        utc = date.utc
        assert utc.year == 2001
        assert utc.month == 1
        assert utc.day == 2

    def test_negative_timestamp(self):
        """Negative timestamp should be before 2001-01-01."""
        # One day before epoch
        date = Date(-86400.0)
        utc = date.utc
        assert utc.year == 2000
        assert utc.month == 12
        assert utc.day == 31

    def test_repr(self):
        """repr should show ISO format date."""
        date = Date(0.0)
        repr_str = repr(date)
        assert "Date(" in repr_str
        assert "2001-01-01" in repr_str


class TestOtherTypes:
    """Tests for remaining NS type wrappers."""

    def test_null_decode_returns_none(self):
        """Null.decode_archive should return None."""
        # Can't easily test without a real archive, but we can test the static method
        class MockArchive:
            pass

        result = Null.decode_archive(MockArchive())
        assert result is None

    def test_value_class_exists(self):
        """Value class should exist and have decode_archive."""
        assert hasattr(Value, "decode_archive")

    def test_mutable_data_class_exists(self):
        """MutableData class should exist and have decode_archive."""
        assert hasattr(MutableData, "decode_archive")

    def test_mutable_string_class_exists(self):
        """MutableString class should exist and have decode_archive."""
        assert hasattr(MutableString, "decode_archive")

    def test_tap_message_class_exists(self):
        """TapMessage class should exist and have decode_archive."""
        assert hasattr(TapMessage, "decode_archive")


class TestArchiverRegistration:
    """Tests for archiver class map registration."""

    def test_nserror_registered(self):
        """NSError should be registered in archiver class map."""
        assert "NSError" in archiver.UNARCHIVE_CLASS_MAP

    def test_nsuuid_registered(self):
        """NSUUID should be registered in archiver class map."""
        assert "NSUUID" in archiver.UNARCHIVE_CLASS_MAP

    def test_nsurl_registered(self):
        """NSURL should be registered in archiver class map."""
        assert "NSURL" in archiver.UNARCHIVE_CLASS_MAP

    def test_nsdate_registered(self):
        """NSDate should be registered in archiver class map."""
        assert "NSDate" in archiver.UNARCHIVE_CLASS_MAP

    def test_nsnull_registered(self):
        """NSNull should be registered in archiver class map."""
        assert "NSNull" in archiver.UNARCHIVE_CLASS_MAP

    def test_tap_messages_registered(self):
        """DTTapMessage variants should be registered."""
        assert "DTTapMessage" in archiver.UNARCHIVE_CLASS_MAP
        assert "DTSysmonTapMessage" in archiver.UNARCHIVE_CLASS_MAP
        assert "DTTapHeartbeatMessage" in archiver.UNARCHIVE_CLASS_MAP
