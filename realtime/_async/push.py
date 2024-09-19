import asyncio
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from realtime.types import DEFAULT_TIMEOUT, Hook, EventCallback

if TYPE_CHECKING:
    from realtime._async.channel import AsyncRealtimeChannel

logger = logging.getLogger(__name__)


class AsyncPush:
    """Handles pushing messages to the server and managing responses."""

    def __init__(
        self,
        channel: "AsyncRealtimeChannel",
        event: str,
        payload: Dict[str, Any],
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Initialize the AsyncPush instance.

        Args:
            channel (AsyncRealtimeChannel): The channel through which the push is sent.
            event (str): The event name.
            payload (Dict[str, Any]): The payload data to send.
            timeout (int): Timeout in seconds for the push operation.
        """
        self.channel = channel
        self.event = event
        self.payload = payload
        self.timeout = timeout
        self._sent = False
        # Generate a unique reference for this push
        self._ref: Optional[str] = self.channel.socket.make_ref()
        self._receipts: List[Hook] = []
        self._awaitable: Optional[asyncio.Future] = None

    async def send(self) -> None:
        """Sends the push to the server."""
        if self._sent:
            logger.warning("Push already sent.")
            return
        # Set shared state before any await
        self._sent = True
        self._awaitable = asyncio.ensure_future(self._wait_for_response())

        # Prepare the envelope to send over the socket
        envelope = {
            "topic": self.channel.topic,
            "event": self.event,
            "payload": self.payload,
            "ref": self._ref,
            "join_ref": self.channel.join_ref,
        }
        try:
            logger.debug(f"Sending push: {envelope}")
            await self.channel.socket.send(envelope)
        except Exception as e:
            logger.error(f"Failed to send push: {e}")
            await self.channel._on_error(e)
            # If sending failed, reset shared state
            self._sent = False
            if self._awaitable and not self._awaitable.done():
                self._awaitable.cancel()
            self._awaitable = None

    async def _wait_for_response(self) -> None:
        """Waits for the server to respond or times out."""
        try:
            await asyncio.wait_for(self._handle_response(), timeout=self.timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Push timed out after {self.timeout} seconds.")
            await self._trigger_receipts("timeout", {})
        except Exception as e:
            logger.error(f"Error while waiting for response: {e}")
            logger.exception(e)

    async def _handle_response(self) -> None:
        """Handles the server's response to the push."""
        event_name = self.channel._reply_event_name(self._ref)
        future = asyncio.get_running_loop().create_future()

        async def callback(payload: Dict[str, Any], ref: Optional[str]) -> None:
            if not future.done():
                future.set_result((payload, ref))

        # Register a one-time listener for the reply
        self.channel.on(event_name, callback)

        try:
            payload, _ = await future
            status = payload.get("status")
            response = payload.get("response", {})
            await self._trigger_receipts(status, response)
        finally:
            # Remove the listener after the response is handled
            self.channel.off(event_name, callback)

    def receive(self, status: str, callback: EventCallback) -> "AsyncPush":
        """
        Registers a callback for a specific response status.

        Args:
            status (str): The status to listen for ('ok', 'error', 'timeout').
            callback (EventCallback): The callback to execute when the status is received.

        Returns:
            AsyncPush: Self, to allow method chaining.
        """
        if not asyncio.iscoroutinefunction(callback):
            raise ValueError("Callback must be an async function.")
        hook = Hook(status=status, callback=callback)
        self._receipts.append(hook)
        return self

    async def _trigger_receipts(self, status: str, response: Any) -> None:
        """Triggers the registered callbacks matching the given status."""
        for receipt in self._receipts:
            if receipt.status == status:
                try:
                    await receipt.callback(response, self._ref)
                except Exception as e:
                    logger.exception(f"Exception in push receipt callback: {e}")

    def cancel(self) -> None:
        """Cancels the push operation if it's still pending."""
        if self._awaitable and not self._awaitable.done():
            self._awaitable.cancel()
            logger.debug("Push operation cancelled.")
