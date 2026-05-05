"""Tests for DTX Message and MessageSender."""

import asyncio
import struct

import pytest
from bpylist2 import archiver

from iosdevice.protocol.message import Message
from iosdevice.protocol.sender import MessageSender
from iosdevice.protocol.constants import MessageType, TransportFlags, MESSAGE_HEADER_SIZE
from iosdevice.protocol.exceptions import ProtocolError
from iosdevice.protocol.ns_types import Error


class TestMessage:
    """Tests for Message dataclass."""

    def test_basic_construction(self):
        """Message should store basic fields."""
        msg = Message(
            type=MessageType.DISPATCH,
            identifier=1,
            channel_code=5,
        )
        assert msg.type == MessageType.DISPATCH
        assert msg.identifier == 1
        assert msg.channel_code == 5
        assert msg.conversation_index == 0

    def test_default_values(self):
        """Message should have sensible defaults."""
        msg = Message(type=MessageType.OK)
        assert msg.identifier == 0
        assert msg.conversation_index == 0
        assert msg.channel_code == 0
        assert msg.flags == 0
        assert msg.transport_flags == TransportFlags.NONE
        assert len(msg.aux_data) == 0
        assert len(msg.payload_data) == 0


class TestMessagePayload:
    """Tests for Message payload encoding/decoding."""

    def test_set_payload(self):
        """Setting payload should archive the object."""
        msg = Message(type=MessageType.OBJECT)
        msg.payload = {"key": "value"}

        assert len(msg.payload_data) > 0
        assert msg.payload == {"key": "value"}

    def test_get_payload(self):
        """Getting payload should unarchive data."""
        original = {"test": [1, 2, 3]}
        archived = archiver.archive(original)

        msg = Message(
            type=MessageType.OBJECT,
            payload_data=memoryview(archived),
        )

        assert msg.payload == original

    def test_none_payload(self):
        """Setting None payload should clear data."""
        msg = Message(type=MessageType.OK)
        msg.payload = None

        assert len(msg.payload_data) == 0
        assert msg.payload is None

    def test_string_payload(self):
        """String payload should work."""
        msg = Message(type=MessageType.DISPATCH)
        msg.payload = "method_name"

        assert msg.payload == "method_name"


class TestMessageAux:
    """Tests for Message auxiliary argument encoding/decoding."""

    def test_set_aux(self):
        """Setting aux should encode arguments."""
        msg = Message(type=MessageType.DISPATCH)
        msg.aux = [{"arg": 1}, "string_arg"]

        assert len(msg.aux_data) > 0

    def test_get_aux(self):
        """Getting aux should decode arguments."""
        msg = Message(type=MessageType.DISPATCH)
        msg.aux = [42, "test", {"nested": True}]

        result = msg.aux
        assert len(result) == 3
        assert result[0] == 42
        assert result[1] == "test"
        assert result[2] == {"nested": True}

    def test_empty_aux(self):
        """Empty aux should work."""
        msg = Message(type=MessageType.DISPATCH)
        msg.aux = []

        assert len(msg.aux_data) == 0
        assert msg.aux == []


class TestMessageValidation:
    """Tests for Message validation."""

    def test_ok_with_payload_invalid(self):
        """OK message with payload should fail validation."""
        msg = Message(type=MessageType.OK)
        msg._payload_cache = "data"
        msg.payload_data = memoryview(b"xxx")

        with pytest.raises(ProtocolError, match="no payload"):
            msg.validate()

    def test_ok_with_aux_invalid(self):
        """OK message with aux data should fail validation."""
        msg = Message(type=MessageType.OK)
        msg.aux_data = memoryview(b"xxx")

        with pytest.raises(ProtocolError, match="no aux"):
            msg.validate()

    def test_error_without_payload_invalid(self):
        """ERROR message without payload should fail validation."""
        msg = Message(type=MessageType.ERROR)

        with pytest.raises(ProtocolError, match="must have a payload"):
            msg.validate()

    def test_error_with_aux_invalid(self):
        """ERROR message with aux should fail validation."""
        msg = Message(type=MessageType.ERROR)
        msg.payload = Error(1, "domain")
        msg.aux_data = memoryview(b"xxx")

        with pytest.raises(ProtocolError, match="no aux"):
            msg.validate()

    def test_reply_with_zero_id_invalid(self):
        """Reply with zero identifier should fail validation."""
        msg = Message(
            type=MessageType.OBJECT,
            conversation_index=1,
            identifier=0,
        )

        with pytest.raises(ProtocolError, match="non-zero identifier"):
            msg.validate()

    def test_reply_wrong_type_invalid(self):
        """Reply with wrong type should fail validation."""
        msg = Message(
            type=MessageType.DISPATCH,
            conversation_index=1,
            identifier=5,
        )

        with pytest.raises(ProtocolError, match="OK/OBJECT/ERROR"):
            msg.validate()

    def test_valid_dispatch(self):
        """Valid DISPATCH should pass validation."""
        msg = Message(type=MessageType.DISPATCH, channel_code=1)
        msg.payload = "method"
        msg.aux = [1, 2, 3]
        msg.validate()  # Should not raise

    def test_valid_reply(self):
        """Valid reply should pass validation."""
        msg = Message(
            type=MessageType.OBJECT,
            conversation_index=1,
            identifier=5,
        )
        msg.payload = "result"
        msg.validate()  # Should not raise


class TestMessageChunks:
    """Tests for Message wire serialization."""

    def test_chunks_returns_three_parts(self):
        """chunks() should return header, aux, and payload."""
        msg = Message(type=MessageType.DISPATCH, channel_code=1)
        msg.payload = "method"
        msg.aux = []

        chunks = msg.chunks()
        assert len(chunks) == 3
        assert len(chunks[0]) == MESSAGE_HEADER_SIZE  # header

    def test_chunks_header_format(self):
        """Header should have correct format."""
        msg = Message(type=MessageType.OBJECT, channel_code=1)
        msg.payload = "test"

        chunks = msg.chunks()
        header = bytes(chunks[0])

        # First byte is message type
        assert header[0] == int(MessageType.OBJECT)

    def test_unsupported_type_raises(self):
        """Unsupported message type should raise."""
        msg = Message(type=MessageType.COMPRESSED)

        with pytest.raises(ProtocolError, match="Unsupported"):
            msg.chunks()


class TestMessageSender:
    """Tests for MessageSender."""

    def test_initial_state(self):
        """Sender should start with no pending replies."""
        sender = MessageSender()
        assert sender.pending_count == 0

    def test_create_dispatch(self):
        """create_dispatch should create DISPATCH message."""
        sender = MessageSender()
        msg = sender.create_dispatch(
            channel_code=1,
            method="doSomething:",
            args=[1, 2, 3],
        )

        assert msg.type == MessageType.DISPATCH
        assert msg.channel_code == 1
        assert msg.payload == "doSomething:"
        assert TransportFlags.EXPECTS_REPLY in msg.transport_flags

    def test_create_dispatch_no_reply(self):
        """create_dispatch with expects_reply=False should not set flag."""
        sender = MessageSender()
        msg = sender.create_dispatch(
            channel_code=1,
            method="fire:",
            expects_reply=False,
        )

        assert TransportFlags.EXPECTS_REPLY not in msg.transport_flags

    def test_create_notification(self):
        """create_notification should create OBJECT message."""
        sender = MessageSender()
        msg = sender.create_notification(
            channel_code=2,
            payload={"event": "happened"},
        )

        assert msg.type == MessageType.OBJECT
        assert msg.channel_code == 2
        assert msg.payload == {"event": "happened"}

    def test_create_notification_with_error(self):
        """create_notification with Error should create ERROR message."""
        sender = MessageSender()
        error = Error(42, "TestDomain")
        msg = sender.create_notification(channel_code=1, payload=error)

        assert msg.type == MessageType.ERROR

    def test_create_notification_none_payload_raises(self):
        """create_notification without payload should raise."""
        sender = MessageSender()
        with pytest.raises(ValueError, match="must have a payload"):
            sender.create_notification(channel_code=1, payload=None)

    def test_create_reply(self):
        """create_reply should create OBJECT reply."""
        sender = MessageSender()
        msg = sender.create_reply(
            channel_code=1,
            msg_id=10,
            conv_idx=1,
            payload="result",
        )

        assert msg.type == MessageType.OBJECT
        assert msg.identifier == 10
        assert msg.conversation_index == 1
        assert msg.payload == "result"

    def test_create_reply_zero_conv_raises(self):
        """create_reply with zero conversation index should raise."""
        sender = MessageSender()
        with pytest.raises(ValueError, match="non-zero"):
            sender.create_reply(channel_code=1, msg_id=10, conv_idx=0)

    def test_create_reply_ack(self):
        """create_reply_ack should create OK message."""
        sender = MessageSender()
        msg = sender.create_reply_ack(
            channel_code=1,
            msg_id=10,
            conv_idx=1,
        )

        assert msg.type == MessageType.OK
        assert msg.identifier == 10
        assert msg.conversation_index == 1

    def test_create_reply_error(self):
        """create_reply_error should create ERROR message."""
        sender = MessageSender()
        error = Error(123, "ErrorDomain", {"info": "detail"})
        msg = sender.create_reply_error(
            channel_code=1,
            msg_id=10,
            conv_idx=1,
            error=error,
        )

        assert msg.type == MessageType.ERROR
        assert msg.identifier == 10
        assert msg.conversation_index == 1

    def test_create_reply_error_non_error_raises(self):
        """create_reply_error with non-Error should raise."""
        sender = MessageSender()
        with pytest.raises(ValueError, match="must be Error"):
            sender.create_reply_error(
                channel_code=1,
                msg_id=10,
                conv_idx=1,
                error="not an error",
            )


class TestMessageSenderAsync:
    """Async tests for MessageSender reply tracking."""

    @pytest.mark.asyncio
    async def test_assign_id(self):
        """assign_id_and_track should assign unique IDs."""
        sender = MessageSender()
        msg1 = Message(type=MessageType.DISPATCH)
        msg2 = Message(type=MessageType.DISPATCH)

        await sender.assign_id_and_track(msg1)
        await sender.assign_id_and_track(msg2)

        assert msg1.identifier == 1
        assert msg2.identifier == 2

    @pytest.mark.asyncio
    async def test_track_expects_reply(self):
        """Messages with EXPECTS_REPLY should be tracked."""
        sender = MessageSender()
        msg = sender.create_dispatch(channel_code=1, method="test")

        await sender.assign_id_and_track(msg)

        assert sender.pending_count == 1

    @pytest.mark.asyncio
    async def test_no_track_without_expects_reply(self):
        """Messages without EXPECTS_REPLY should not be tracked."""
        sender = MessageSender()
        msg = sender.create_dispatch(channel_code=1, method="test", expects_reply=False)

        await sender.assign_id_and_track(msg)

        assert sender.pending_count == 0

    @pytest.mark.asyncio
    async def test_resolve_reply(self):
        """resolve_reply should complete the future."""
        sender = MessageSender()
        msg = sender.create_dispatch(channel_code=1, method="test")
        await sender.assign_id_and_track(msg)

        response = Message(type=MessageType.OBJECT)
        response.payload = "result"

        resolved = sender.resolve_reply(msg.identifier, response)
        assert resolved is True
        assert sender.pending_count == 0

    @pytest.mark.asyncio
    async def test_wait_for_reply(self):
        """wait_for_reply should return the response."""
        sender = MessageSender()
        msg = sender.create_dispatch(channel_code=1, method="test")
        await sender.assign_id_and_track(msg)

        response = Message(type=MessageType.OBJECT)
        response.payload = "result"

        # Simulate receiving reply in background
        async def send_reply():
            await asyncio.sleep(0.01)
            sender.resolve_reply(msg.identifier, response)

        task = asyncio.create_task(send_reply())

        result = await sender.wait_for_reply(msg.identifier)
        assert result is response

        await task

    @pytest.mark.asyncio
    async def test_wait_for_nonexistent_raises(self):
        """wait_for_reply for unknown ID should raise."""
        sender = MessageSender()

        with pytest.raises(ValueError, match="No pending"):
            await sender.wait_for_reply(999)

    @pytest.mark.asyncio
    async def test_cancel_pending(self):
        """cancel_pending should cancel the future."""
        sender = MessageSender()
        msg = sender.create_dispatch(channel_code=1, method="test")
        await sender.assign_id_and_track(msg)

        cancelled = sender.cancel_pending(msg.identifier)
        assert cancelled is True
        assert sender.pending_count == 0

    @pytest.mark.asyncio
    async def test_cancel_all_pending(self):
        """cancel_all_pending should cancel all futures."""
        sender = MessageSender()

        for i in range(5):
            msg = sender.create_dispatch(channel_code=1, method=f"test{i}")
            await sender.assign_id_and_track(msg)

        assert sender.pending_count == 5

        count = sender.cancel_all_pending()
        assert count == 5
        assert sender.pending_count == 0


class TestMessageRepr:
    """Tests for Message string representation."""

    def test_repr_basic(self):
        """repr should show key fields."""
        msg = Message(
            type=MessageType.DISPATCH,
            identifier=42,
            channel_code=5,
        )
        msg.payload = "method"

        repr_str = repr(msg)
        assert "Message:" in repr_str
        assert "DISPATCH" in repr_str
        assert "i42" in repr_str
        assert "c5" in repr_str

    def test_repr_with_expects_reply(self):
        """repr should show 'e' for expects reply."""
        msg = Message(
            type=MessageType.DISPATCH,
            identifier=1,
            transport_flags=TransportFlags.EXPECTS_REPLY,
        )

        repr_str = repr(msg)
        assert "i1.0e" in repr_str
