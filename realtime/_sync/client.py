import asyncio
import json
import logging
import re
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Union

import websockets

from ..exceptions import NotConnectedError
from ..message import Message
from ..transformers import http_endpoint_url
from ..types import (
    DEFAULT_TIMEOUT,
    PHOENIX_CHANNEL,
    Callback,
    ChannelEvents,
    T_ParamSpec,
    T_Retval,
)
from .channel import RealtimeChannelOptions, SyncRealtimeChannel

logger = logging.getLogger(__name__)


def ensure_connection(func: Callback):
    @wraps(func)
    def wrapper(*args: T_ParamSpec.args, **kwargs: T_ParamSpec.kwargs) -> T_Retval:
        if not args[0].is_connected:
            raise NotConnectedError(func.__name__)

        return func(*args, **kwargs)

    return wrapper


class SyncRealtimeClient:
    def __init__(
        self,
        url: str,
        token: str,
        auto_reconnect: bool = False,
        params: Dict[str, Any] = {},
        hb_interval: int = 30,
        max_retries: int = 5,
        initial_backoff: float = 1.0,
    ) -> None:
        """
        Initialize a RealtimeClient instance for WebSocket communication.

        :param url: WebSocket URL of the Realtime server. Starts with `ws://` or `wss://`.
                    Also accepts default Supabase URL: `http://` or `https://`.
        :param token: Authentication token for the WebSocket connection.
        :param auto_reconnect: If True, automatically attempt to reconnect on disconnection. Defaults to False.
        :param params: Optional parameters for the connection. Defaults to an empty dictionary.
        :param hb_interval: Interval (in seconds) for sending heartbeat messages to keep the connection alive. Defaults to 30.
        :param max_retries: Maximum number of reconnection attempts. Defaults to 5.
        :param initial_backoff: Initial backoff time (in seconds) for reconnection attempts. Defaults to 1.0.
        """
        self.url = f"{re.sub(r'https://', 'wss://', re.sub(r'http://', 'ws://', url, flags=re.IGNORECASE), flags=re.IGNORECASE)}/websocket?apikey={token}"
        self.http_endpoint = http_endpoint_url(url)
        self.is_connected = False
        self.params = params
        self.apikey = token
        self.access_token = token
        self.send_buffer: List[Callable] = []
        self.hb_interval = hb_interval
        self.ws_connection: Optional[websockets.client.WebSocketClientProtocol] = None
        self.ref = 0
        self.auto_reconnect = auto_reconnect
        self.channels: Dict[str, SyncRealtimeChannel] = {}
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.timeout = DEFAULT_TIMEOUT

    def _listen(self) -> None:
        """
        An infinite loop that keeps listening.
        :return: None
        """
        while True:
            try:
                msg = self.ws_connection.recv()
                logger.info(f"receive: {msg}")

                msg = Message(**json.loads(msg))
                channel = self.channels.get(msg.topic)

                if channel:
                    channel._trigger(msg.event, msg.payload, msg.ref)
                else:
                    logger.info(f"Channel {msg.topic} not found")

            except websockets.exceptions.ConnectionClosed:
                if self.auto_reconnect:
                    logger.info("Connection with server closed, trying to reconnect...")
                    self._connect()
                    for topic, channel in self.channels.items():
                        channel.join()
                else:
                    logger.exception("Connection with the server closed.")
                    break

    def connect(self) -> None:
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
        retries = 0
        backoff = self.initial_backoff

        while retries < self.max_retries:
            try:
                self.ws_connection = websockets.connect(self.url)
                if self.ws_connection.open:
                    logger.info("Connection was successful")
                    return self._on_connect()
                else:
                    raise Exception("Failed to open WebSocket connection")
            except Exception as e:
                retries += 1
                if retries >= self.max_retries or not self.auto_reconnect:
                    logger.error(
                        f"Failed to establish WebSocket connection after {retries} attempts: {e}"
                    )
                    raise
                else:
                    wait_time = backoff * (2 ** (retries - 1))  # Exponential backoff
                    logger.info(
                        f"Connection attempt {retries} failed. Retrying in {wait_time:.2f} seconds..."
                    )
                    asyncio.sleep(wait_time)
                    backoff = min(backoff * 2, 60)  # Cap the backoff at 60 seconds

        raise Exception(
            f"Failed to establish WebSocket connection after {self.max_retries} attempts"
        )

    def listen(self):
        asyncio.gather(self._listen(), self._heartbeat())

    def _on_connect(self):
        self.is_connected = True
        self._flush_send_buffer()

    def _flush_send_buffer(self):
        if self.is_connected and len(self.send_buffer) > 0:
            for callback in self.send_buffer:
                callback()
            self.send_buffer = []

    @ensure_connection
    def close(self) -> None:
        """
        Close the WebSocket connection.

        Returns:
            None

        Raises:
            NotConnectedError: If the connection is not established when this method is called.
        """

        self.ws_connection.close()
        self.is_connected = False

    def _heartbeat(self) -> None:
        while self.is_connected:
            try:
                data = dict(
                    topic=PHOENIX_CHANNEL,
                    event=ChannelEvents.heartbeat,
                    payload={},
                    ref=None,
                )
                self.send(data)
                asyncio.sleep(self.hb_interval)
            except websockets.exceptions.ConnectionClosed:
                if self.auto_reconnect:
                    logger.info("Connection with server closed, trying to reconnect...")
                    self._connect()
                else:
                    logger.exception("Connection with the server closed.")
                    break

    @ensure_connection
    def channel(
        self, topic: str, params: RealtimeChannelOptions = {}
    ) -> SyncRealtimeChannel:
        """
        :param topic: Initializes a channel and creates a two-way association with the socket
        :return: Channel
        """
        topic = f"realtime:{topic}"
        chan = SyncRealtimeChannel(self, topic, params)
        self.channels[topic] = chan

        return chan

    def get_channels(self) -> List[SyncRealtimeChannel]:
        return list(self.channels.values())

    def remove_channel(self, channel: SyncRealtimeChannel) -> None:
        """
        Unsubscribes and removes a channel from the socket
        :param channel: Channel to remove
        :return: None
        """
        if channel.topic in self.channels:
            self.channels[channel.topic].unsubscribe()
            del self.channels[channel.topic]

        if len(self.channels) == 0:
            self.close()

    def remove_all_channels(self) -> None:
        """
        Unsubscribes and removes all channels from the socket
        :return: None
        """
        for _, channel in self.channels.items():
            channel.unsubscribe()

        self.close()

    def summary(self) -> None:
        """
        Prints a list of topics and event the socket is listening to
        :return: None
        """
        for topic, channel in self.channels.items():
            print(f"Topic: {topic} | Events: {[e for e, _ in channel.listeners]}]")

    @ensure_connection
    def set_auth(self, token: Union[str, None]) -> None:
        """
        Set the authentication token for the connection and update all joined channels.

        This method updates the access token for the current connection and sends the new token
        to all joined channels. This is useful for refreshing authentication or changing users.

        Args:
            token (Union[str, None]): The new authentication token. Can be None to remove authentication.

        Returns:
            None
        """
        self.access_token = token

        for _, channel in self.channels.items():
            if channel._joined_once and channel.is_joined:
                channel.push(ChannelEvents.access_token, {"access_token": token})

    def _make_ref(self) -> str:
        self.ref += 1
        return f"{self.ref}"

    def send(self, message: Dict[str, Any]) -> None:
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

        Raises:
            websockets.exceptions.WebSocketException: If there's an error sending the message.
        """

        message = json.dumps(message)
        logging.info(f"send: {message}")

        def send_message():
            self.ws_connection.send(message)

        if self.is_connected:
            send_message()
        else:
            self.send_buffer.append(send_message)

    def _leave_open_topic(self, topic: str):
        dup_channels = [
            ch
            for ch in self.channels.values()
            if ch.topic == topic and (ch.is_joined or ch.is_joining)
        ]

        for ch in dup_channels:
            ch.unsubscribe()
