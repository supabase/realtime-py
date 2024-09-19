import asyncio
import json
import logging
from typing import Any, Dict, Optional

import websockets

from realtime._async.channel import AsyncRealtimeChannel
from realtime._async.timer import AsyncTimer
from realtime.exceptions import (
    ConnectionFailedError,
    NotConnectedError,
)
from realtime.message import Message
from realtime.transformers import http_to_websocket_url
from realtime.types import (
    DEFAULT_TIMEOUT,
    ChannelEvents,
    PHOENIX_CHANNEL,
    RealtimeChannelConfig,
)

logger = logging.getLogger(__name__)


class AsyncRealtimeClient:
    """Manages the WebSocket connection and orchestrates channels."""

    def __init__(
        self,
        url: str,
        token: str,
        params: Optional[Dict[str, Any]] = None,
        hb_interval: int = 30,
        max_retries: int = 5,
        initial_backoff: float = 1.0,
        auto_reconnect: bool = True,
    ) -> None:
        """
        Initialize the AsyncRealtimeClient.

        Args:
            url (str): The WebSocket URL of the server.
            token (str): The authentication token (e.g., API key).
            params (Optional[Dict[str, Any]]): Additional parameters for the connection.
            hb_interval (int): Heartbeat interval in seconds.
            max_retries (int): Maximum number of connection retries.
            initial_backoff (float): Initial backoff time in seconds for retries.
            auto_reconnect (bool): Whether to auto-reconnect on disconnection.
        """
        self.url = url
        self.access_token = token
        self.params = params or {}
        self.hb_interval = hb_interval
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.auto_reconnect = auto_reconnect

        self.timeout = DEFAULT_TIMEOUT

        self.is_connected: bool = False
        self.is_reconnecting: bool = False
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._send_lock = asyncio.Lock()
        self._channels: Dict[str, AsyncRealtimeChannel] = {}
        self._ref: int = 0
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_timer: AsyncTimer = AsyncTimer(
            self._attempt_reconnect, self._calculate_reconnect_delay
        )

    async def connect(self) -> None:
        """Establishes a WebSocket connection with retry logic."""
        if self.is_connected:
            return
        retries = 0
        last_exception = None
        backoff = self.initial_backoff

        # Prepare the WebSocket URL with the auth token
        websocket_url = http_to_websocket_url(
            self.url,
            params={"apikey": self.access_token} if self.access_token else {},
        )

        while retries < self.max_retries:
            try:
                ws = await websockets.connect(websocket_url)
                # Only modify shared state after successful connection
                self._ws = ws
                self.is_connected = True
                logger.info(f"WebSocket connection established to {websocket_url}.")
                self._receive_task = asyncio.create_task(self._receive_loop())
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                self._reconnect_timer.reset()
                return
            except Exception as e:
                retries += 1
                last_exception = e
                logger.warning(f"Connection attempt {retries} failed: {e}")
                await asyncio.sleep(backoff)
                backoff *= 2
        logger.error(f"Failed to establish connection after {retries} attempts.")
        raise ConnectionFailedError(retries, last_exception)

    async def disconnect(self) -> None:
        """Closes the WebSocket connection."""
        if not self.is_connected:
            return
        self.is_connected = False
        if self._ws:
            await self._ws.close()
        if self._receive_task:
            self._receive_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        # Notify channels
        for channel in self._channels.values():
            await channel._on_disconnect()
        self._reconnect_timer.reset()
        logger.info("WebSocket connection closed.")

    def channel(
        self, topic: str, params: Optional[RealtimeChannelConfig] = None
    ) -> AsyncRealtimeChannel:
        """
        Creates a new channel or returns an existing one.

        Args:
            topic (str): The topic string.
            params (Optional[RealtimeChannelConfig]): Optional channel configuration.

        Returns:
            AsyncRealtimeChannel: The channel object.
        """
        full_topic = f"realtime:{topic}"
        if full_topic in self._channels:
            return self._channels[full_topic]
        channel = AsyncRealtimeChannel(self, full_topic, params)
        self._channels[full_topic] = channel
        return channel

    async def remove_channel(self, channel: AsyncRealtimeChannel) -> None:
        """Removes a channel."""
        await channel.unsubscribe()
        self._channels.pop(channel.topic, None)

    async def send(self, message: Dict[str, Any]) -> None:
        """
        Sends a message over the WebSocket connection.

        Args:
            message (Dict[str, Any]): The message to send.

        Raises:
            NotConnectedError: If the client is not connected.
        """
        async with self._send_lock:
            if not self.is_connected or not self._ws:
                raise NotConnectedError("send")
            try:
                await self._ws.send(json.dumps(message))
                logger.debug(f"Sent message: {message}")
            except Exception as e:
                await self._handle_connection_error(e)

    async def _receive_loop(self) -> None:
        """Listens for incoming messages and dispatches them to channels."""
        try:
            async for raw_message in self._ws:
                message = json.loads(raw_message)
                logger.debug(f"Received message: {message}")
                await self._handle_message(message)
        except Exception as e:
            await self._handle_connection_error(e)

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handles a received message from the server."""
        msg = Message(**message)
        channel = self._channels.get(msg.topic)

        if channel:
            # Dispatch the message to the appropriate channel
            await channel._trigger(msg.event, msg.payload, msg.ref)
        else:
            if msg.topic == PHOENIX_CHANNEL:
                # This is a heartbeat reply or other Phoenix-level message
                if msg.event == ChannelEvents.REPLY.value and msg.ref:
                    logger.debug(f"Heartbeat reply received: {message}")
                else:
                    logger.debug(f"Received message on topic '{msg.topic}': {message}")
            else:
                # Unexpected message without an associated channel
                logger.warning(f"No channel found for topic: {msg.topic}")

    async def _heartbeat_loop(self) -> None:
        """Sends heartbeat messages at regular intervals."""
        while self.is_connected:
            try:
                heartbeat_message = {
                    "topic": PHOENIX_CHANNEL,
                    "event": ChannelEvents.HEARTBEAT.value,
                    "payload": {},
                    "ref": self.make_ref(),
                }
                await self.send(heartbeat_message)
                logger.debug("Heartbeat sent.")
            except Exception as e:
                await self._handle_connection_error(e)
                break  # Exit the loop as reconnection will be handled

            await asyncio.sleep(self.hb_interval)

    async def _handle_connection_error(self, error: Exception) -> None:
        """Handles connection errors and initiates reconnection if enabled."""
        logger.exception(f"Connection error occurred: {error}")
        if self.is_connected:
            self.is_connected = False
            # Notify channels of disconnection
            for channel in self._channels.values():
                await channel._on_disconnect()
            if self.auto_reconnect and not self.is_reconnecting:
                self.is_reconnecting = True
                self._reconnect_timer.reset()
                self._reconnect_timer.schedule()
            else:
                await self.disconnect()

    async def _attempt_reconnect(self) -> None:
        """Attempts to reconnect to the server."""
        logger.info("Attempting to reconnect to the WebSocket server.")
        if self.is_reconnecting:
            return
        self.is_reconnecting = True
        try:
            await self.disconnect()
            await self.connect()
            # Rejoin channels
            for channel in self._channels.values():
                if channel.auto_rejoin:
                    await channel.subscribe()
                else:
                    logger.debug(f"Auto rejoin is disabled for channel: {channel.topic}")
        except Exception as e:
            logger.exception(f"Reconnection attempt failed: {e}")
        finally:
            self.is_reconnecting = False

    def _calculate_reconnect_delay(self, tries: int) -> float:
        """Calculates the delay before attempting to reconnect."""
        return min(self.initial_backoff * (2 ** (tries - 1)), 30.0)

    def make_ref(self) -> str:
        """Generates a new unique reference."""
        self._ref += 1
        return str(self._ref)

    async def set_auth(self, token: Optional[str]) -> None:
        """
        Set the authentication token for the connection and update all joined channels.

        Args:
            token (Optional[str]): The new authentication token.

        Returns:
            None
        """
        self.access_token = token

        # Send access_token messages to all channels
        for channel in self._channels.values():
            await channel.update_access_token(token)
