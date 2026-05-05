"""DTX message sending and reply tracking."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence

from .constants import MessageType, TransportFlags
from .message import Message
from .ns_types import Error


logger = logging.getLogger(__name__)


class MessageSender:
    """Handles outgoing DTX message creation and reply tracking.

    This class manages message identifiers, tracks pending replies,
    and provides methods for sending different types of messages.
    """

    def __init__(self):
        self._next_id: int = 1
        self._pending_replies: dict[int, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    @property
    def pending_count(self) -> int:
        """Number of pending reply futures."""
        return len(self._pending_replies)

    def _next_identifier(self) -> int:
        """Get the next message identifier."""
        msg_id = self._next_id
        self._next_id += 1
        return msg_id

    def create_dispatch(
        self,
        channel_code: int,
        method: str,
        args: Sequence[Any] = (),
        expects_reply: bool = True,
    ) -> Message:
        """Create a DISPATCH message for method invocation.

        Args:
            channel_code: Target channel code.
            method: Method selector name.
            args: Arguments for the method call.
            expects_reply: Whether to expect a reply.

        Returns:
            A Message object ready for transmission.
        """
        msg = Message(
            type=MessageType.DISPATCH,
            channel_code=channel_code,
            transport_flags=TransportFlags.EXPECTS_REPLY if expects_reply else TransportFlags.NONE,
        )
        msg.payload = method
        msg.aux = args
        return msg

    def create_notification(
        self,
        channel_code: int,
        payload: Any,
        aux_args: Sequence[Any] = (),
        expects_reply: bool = False,
    ) -> Message:
        """Create an OBJECT notification message.

        Args:
            channel_code: Target channel code.
            payload: Payload object to send.
            aux_args: Auxiliary arguments.
            expects_reply: Whether to expect a reply.

        Returns:
            A Message object ready for transmission.
        """
        if payload is None:
            raise ValueError("Notifications must have a payload")

        msg_type = MessageType.ERROR if isinstance(payload, Error) else MessageType.OBJECT
        msg = Message(
            type=msg_type,
            channel_code=channel_code,
            transport_flags=TransportFlags.EXPECTS_REPLY if expects_reply else TransportFlags.NONE,
        )
        msg.payload = payload
        msg.aux = aux_args
        return msg

    def create_reply(
        self,
        channel_code: int,
        msg_id: int,
        conv_idx: int,
        payload: Any = None,
        aux_args: Sequence[Any] = (),
    ) -> Message:
        """Create an OBJECT reply message.

        Args:
            channel_code: Target channel code.
            msg_id: Original message identifier being replied to.
            conv_idx: Conversation index for the reply.
            payload: Payload object.
            aux_args: Auxiliary arguments.

        Returns:
            A Message object ready for transmission.
        """
        if conv_idx == 0:
            raise ValueError("Reply must have non-zero conversation index")

        msg = Message(
            type=MessageType.OBJECT,
            identifier=msg_id,
            conversation_index=conv_idx,
            channel_code=channel_code,
            transport_flags=TransportFlags.NONE,
        )
        msg.payload = payload
        msg.aux = aux_args
        return msg

    def create_reply_ack(
        self,
        channel_code: int,
        msg_id: int,
        conv_idx: int,
    ) -> Message:
        """Create an OK acknowledgment reply.

        Args:
            channel_code: Target channel code.
            msg_id: Original message identifier being replied to.
            conv_idx: Conversation index for the reply.

        Returns:
            A Message object ready for transmission.
        """
        if conv_idx == 0:
            raise ValueError("Reply must have non-zero conversation index")

        return Message(
            type=MessageType.OK,
            identifier=msg_id,
            conversation_index=conv_idx,
            channel_code=channel_code,
            transport_flags=TransportFlags.NONE,
        )

    def create_reply_error(
        self,
        channel_code: int,
        msg_id: int,
        conv_idx: int,
        error: Error,
    ) -> Message:
        """Create an ERROR reply message.

        Args:
            channel_code: Target channel code.
            msg_id: Original message identifier being replied to.
            conv_idx: Conversation index for the reply.
            error: The Error object to send.

        Returns:
            A Message object ready for transmission.
        """
        if conv_idx == 0:
            raise ValueError("Reply must have non-zero conversation index")
        if not isinstance(error, Error):
            raise ValueError(f"ERROR reply payload must be Error, got {type(error)}")

        msg = Message(
            type=MessageType.ERROR,
            identifier=msg_id,
            conversation_index=conv_idx,
            channel_code=channel_code,
            transport_flags=TransportFlags.NONE,
        )
        msg.payload = error
        return msg

    async def assign_id_and_track(self, message: Message) -> None:
        """Assign an identifier and optionally track for reply.

        Args:
            message: The message to prepare for sending.
        """
        async with self._lock:
            if message.identifier == 0:
                message.identifier = self._next_identifier()

            if TransportFlags.EXPECTS_REPLY in message.transport_flags:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self._pending_replies[message.identifier] = future

    def resolve_reply(self, msg_id: int, response: Message) -> bool:
        """Resolve a pending reply with the given response.

        Args:
            msg_id: The message identifier.
            response: The response message.

        Returns:
            True if the reply was pending and resolved, False otherwise.
        """
        future = self._pending_replies.pop(msg_id, None)
        if future is not None and not future.done():
            future.set_result(response)
            return True
        return False

    def cancel_pending(self, msg_id: int) -> bool:
        """Cancel a pending reply.

        Args:
            msg_id: The message identifier.

        Returns:
            True if a pending reply was cancelled, False otherwise.
        """
        future = self._pending_replies.pop(msg_id, None)
        if future is not None and not future.done():
            future.cancel()
            return True
        return False

    async def wait_for_reply(self, msg_id: int) -> Message:
        """Wait for a reply to the given message.

        Args:
            msg_id: The message identifier.

        Returns:
            The response message.

        Raises:
            ValueError: If no reply is pending for this message.
        """
        future = self._pending_replies.get(msg_id)
        if future is None:
            raise ValueError(f"No pending reply for message {msg_id}")

        try:
            return await future
        except asyncio.CancelledError:
            raise
        finally:
            # Remove from tracking after await completes or fails
            self._pending_replies.pop(msg_id, None)

    def cancel_all_pending(self) -> int:
        """Cancel all pending replies.

        Returns:
            Number of cancelled replies.
        """
        count = 0
        for future in list(self._pending_replies.values()):
            if not future.done():
                future.cancel()
                count += 1
        self._pending_replies.clear()
        return count
