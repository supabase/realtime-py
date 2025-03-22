import asyncio
import json
import logging
import re
from base64 import b64decode
from datetime import datetime
from functools import wraps
from math import floor
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode, urlparse, urlunparse

import websockets
from websockets import connect
from websockets.client import ClientProtocol

from ..message import Message
from ..transformers import http_endpoint_url
from ..types import (
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_TIMEOUT,
    PHOENIX_CHANNEL,
    VSN,
    ChannelEvents,
)
from ..utils import is_ws_url
from .channel import AsyncRealtimeChannel, RealtimeChannelOptions


def deprecated(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.warning(f"Warning: {func.__name__} is deprecated.")
        return func(*args, **kwargs)

    return wrapper


logger = logging.getLogger(__name__)


class AsyncRealtimeClient:
    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        auto_reconnect: bool = True,
        params: Optional[Dict[str, Any]] = None,
        hb_interval: int = DEFAULT_HEARTBEAT_INTERVAL,
        max_retries: int = 5,
        initial_backoff: float = 1.0,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Initialize a RealtimeClient instance for WebSocket communication.

        :param url: WebSocket URL of the Realtime server. Starts with `ws://` or `wss://`.
                   Also accepts default Supabase URL: `http://` or `https://`.
        :param token: Authentication token for the WebSocket connection.
        :param auto_reconnect: If True, automatically attempt to reconnect on disconnection. Defaults to True.
        :param params: Optional parameters for the connection. Defaults to None.
        :param hb_interval: Interval (in seconds) for sending heartbeat messages to keep the connection alive. Defaults to 25.
        :param max_retries: Maximum number of reconnection attempts. Defaults to 5.
        :param initial_backoff: Initial backoff time (in seconds) for reconnection attempts. Defaults to 1.0.
        :param timeout: Connection timeout in seconds. Defaults to DEFAULT_TIMEOUT.
        """
        if not is_ws_url(url):
            ValueError("url must be a valid WebSocket URL or HTTP URL string")
        self.url = f"{re.sub(r'https://', 'wss://', re.sub(r'http://', 'ws://', url, flags=re.IGNORECASE), flags=re.IGNORECASE)}/websocket"
        if token:
            self.url += f"?apikey={token}"
        self.http_endpoint = http_endpoint_url(url)
        self.params = params or {}
        self.apikey = token
        self.access_token = token
        self.send_buffer: List[Callable] = []
        self.hb_interval = hb_interval
        self.ws_connection: Optional[ClientProtocol] = None
        self.ref = 0
        self.auto_reconnect = auto_reconnect
        self.channels: Dict[str, AsyncRealtimeChannel] = {}
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.timeout = timeout
        self._listen_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    @property
    def is_connected(self) -> bool:
        return self.ws_connection is not None

    async def _listen(self) -> None:
        """
        An infinite loop that keeps listening.
        :return: None
        """

        if not self.ws_connection:
            raise Exception("WebSocket connection not established")

        try:
            async for msg in self.ws_connection:
                logger.info(f"receive: {msg}")

                msg = Message(**json.loads(msg))
                channel = self.channels.get(msg.topic)

                if channel:
                    channel._trigger(msg.event, msg.payload, msg.ref)
        except websockets.exceptions.ConnectionClosedError as e:
            logger.error(
                f"WebSocket connection closed with code: {e.code}, reason: {e.reason}"
            )
            if self.auto_reconnect:
                logger.info("Initiating auto-reconnect sequence...")

                await self._reconnect()
            else:
                logger.error("Auto-reconnect disabled, terminating connection")

    async def _reconnect(self) -> None:
        self.ws_connection = None
        await self.connect()

        if self.is_connected:
            for topic, channel in self.channels.items():
                logger.info(f"Rejoining channel after reconnection: {topic}")
                await channel._rejoin()

    async def connect(self) -> None:
        """
        Establishes a WebSocket connection with exponential backoff retry mechanism.

        This method attempts to connect to the WebSocket server. If the connection fails,
        it will retry with an exponential backoff strategy up to a maximum number of retries.

        Returns:
            None

        Raises:
            Exception: If unable to establish a connection after max_retries attempts.

        Note:
            - The initial backoff time and maximum retries are set during RealtimeClient initialization.
            - The backoff time doubles after each failed attempt, up to a maximum of 60 seconds.
        """

        if self.is_connected:
            logger.info("WebSocket connection already established")
            return

        retries = 0
        backoff = self.initial_backoff

        logger.info(f"Attempting to connect to WebSocket at {self.url}")

        while retries < self.max_retries:
            try:
                ws = await connect(self.url)
                self.ws_connection = ws
                logger.info("WebSocket connection established successfully")
                return await self._on_connect()
            except Exception as e:
                retries += 1
                logger.error(f"Connection attempt failed: {str(e)}")

                if retries >= self.max_retries or not self.auto_reconnect:
                    logger.error(
                        f"Connection failed permanently after {retries} attempts. Error: {str(e)}"
                    )
                    raise
                else:
                    wait_time = backoff * (2 ** (retries - 1))
                    logger.info(
                        f"Retry {retries}/{self.max_retries}: Next attempt in {wait_time:.2f}s (backoff={backoff}s)"
                    )
                    await asyncio.sleep(wait_time)
                    backoff = min(backoff * 2, 60)

        raise Exception(
            f"Failed to establish WebSocket connection after {self.max_retries} attempts"
        )

    @deprecated
    async def listen(self):
        pass

    async def _on_connect(self) -> None:
        if self._listen_task:
            self._listen_task.cancel()
            self._listen_task = None

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        self._listen_task = asyncio.create_task(self._listen())
        self._heartbeat_task = asyncio.create_task(self._heartbeat())
        await self._flush_send_buffer()

    async def _flush_send_buffer(self):
        if self.is_connected and len(self.send_buffer) > 0:
            for callback in self.send_buffer:
                await callback()
            self.send_buffer = []

    async def close(self) -> None:
        """
        Close the WebSocket connection.

        Returns:
            None

        Raises:
            NotConnectedError: If the connection is not established when this method is called.
        """

        if self.ws_connection:
            await self.ws_connection.close()

        self.ws_connection = None

        if self._listen_task:
            self._listen_task.cancel()
            self._listen_task = None

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def _heartbeat(self) -> None:
        if not self.ws_connection:
            raise Exception("WebSocket connection not established")

        while self.is_connected:
            try:
                data = dict(
                    topic=PHOENIX_CHANNEL,
                    event=ChannelEvents.heartbeat,
                    payload={},
                    ref=None,
                )
                await self.send(data)
                await asyncio.sleep(max(self.hb_interval, 15))

            except websockets.exceptions.ConnectionClosed as e:
                logger.error(
                    f"Connection closed during heartbeat. Code: {e.code}, reason: {e.reason}"
                )

                if self.auto_reconnect:
                    logger.info("Heartbeat failed - initiating reconnection sequence")
                    await self._reconnect()
                else:
                    logger.error("Heartbeat failed - auto-reconnect disabled")
                    break

    def channel(
        self, topic: str, params: Optional[RealtimeChannelOptions] = None
    ) -> AsyncRealtimeChannel:
        """
        Initialize a channel and create a two-way association with the socket.

        :param topic: The topic to subscribe to
        :param params: Optional channel parameters
        :return: AsyncRealtimeChannel instance
        """
        topic = f"realtime:{topic}"
        chan = AsyncRealtimeChannel(self, topic, params)
        self.channels[topic] = chan

        return chan

    def get_channels(self) -> List[AsyncRealtimeChannel]:
        return list(self.channels.values())

    def _remove_channel(self, channel: AsyncRealtimeChannel) -> None:
        del self.channels[channel.topic]

    async def remove_channel(self, channel: AsyncRealtimeChannel) -> None:
        """
        Unsubscribes and removes a channel from the socket
        :param channel: Channel to remove
        :return: None
        """
        if channel.topic in self.channels:
            await self.channels[channel.topic].unsubscribe()

        if len(self.channels) == 0:
            await self.close()

    async def remove_all_channels(self) -> None:
        """
        Unsubscribes and removes all channels from the socket
        :return: None
        """
        for _, channel in self.channels.items():
            await channel.unsubscribe()

        await self.close()

    def summary(self) -> None:
        """
        Prints a list of topics and event the socket is listening to
        :return: None
        """
        for topic, channel in self.channels.items():
            print(f"Topic: {topic} | Events: {[e for e, _ in channel.listeners]}]")

    async def set_auth(self, token: Optional[str]) -> None:
        """
        Set the authentication token for the connection and update all joined channels.

        This method updates the access token for the current connection and sends the new token
        to all joined channels. This is useful for refreshing authentication or changing users.

        Args:
            token (Optional[str]): The new authentication token. Can be None to remove authentication.

        Returns:
            None
        """
        # No empty string tokens.
        if isinstance(token, str) and len(token.strip()) == 0:
            raise ValueError("Provide a valid jwt token")

        if token:
            parsed = None
            try:
                payload = token.split(".")[1] + "=="
                parsed = json.loads(b64decode(payload).decode("utf-8"))
            except Exception:
                raise ValueError("InvalidJWTToken")

            if parsed:
                # Handle expired token if any.
                if "exp" in parsed:
                    now = floor(datetime.now().timestamp())
                    valid = now - parsed["exp"] < 0
                    if not valid:
                        raise ValueError(
                            f"InvalidJWTToken: Invalid value for JWT claim 'exp' with value { parsed['exp'] }"
                        )
                else:
                    raise ValueError("InvalidJWTToken: expected claim 'exp'")

        self.access_token = token

        for _, channel in self.channels.items():
            if channel._joined_once and channel.is_joined:
                await channel.push(ChannelEvents.access_token, {"access_token": token})

    def _make_ref(self) -> str:
        self.ref += 1
        return f"{self.ref}"

    async def send(self, message: Dict[str, Any]) -> None:
        """
        Send a message through the WebSocket connection.

        This method serializes the given message dictionary to JSON,
        and sends it through the WebSocket connection. If the connection
        is not currently established, the message will be buffered and sent
        once the connection is re-established.

        Args:
            message (Dict[str, Any]): The message to be sent, as a dictionary.

        Returns:
            None
        """

        message = json.dumps(message)
        logger.info(f"send: {message}")

        async def send_message():
            await self.ws_connection.send(message)

        if self.is_connected:
            await send_message()
        else:
            self.send_buffer.append(send_message)

    async def _leave_open_topic(self, topic: str):
        dup_channels = [
            ch
            for ch in self.channels.values()
            if ch.topic == topic and (ch.is_joined or ch.is_joining)
        ]

        for ch in dup_channels:
            await ch.unsubscribe()

    def endpoint_url(self) -> str:
        parsed_url = urlparse(self.url)
        query = urlencode({**self.params, "vsn": VSN}, doseq=True)
        return urlunparse(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                query,
                parsed_url.fragment,
            )
        )
