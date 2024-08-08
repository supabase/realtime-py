import asyncio
import json
import logging
import re
from functools import wraps
from typing import Any, Dict, Union

import websockets

from realtime.channel import Channel
from realtime.exceptions import NotConnectedError
from realtime.message import HEARTBEAT_PAYLOAD, PHOENIX_CHANNEL, ChannelEvents, Message
from realtime.transformers import http_endpoint_url
from realtime.types import Callback, T_ParamSpec, T_Retval

logging.basicConfig(
    format="%(asctime)s:%(levelname)s - %(message)s", level=logging.INFO
)

logger = logging.getLogger(__name__)


def ensure_connection(func: Callback):
    @wraps(func)
    def wrapper(*args: T_ParamSpec.args, **kwargs: T_ParamSpec.kwargs) -> T_Retval:
        if not args[0].is_connected:
            raise NotConnectedError(func.__name__)

        return func(*args, **kwargs)

    return wrapper


class Socket:
    def __init__(
        self,
        url: str,
        token: str,
        auto_reconnect: bool = False,
        params: Dict[str, Any] = {},
        hb_interval: int = 5,
        max_retries: int = 5,
        initial_backoff: float = 1.0,
    ) -> None:
        """
        `Socket` is the abstraction for an actual socket connection that receives and 'reroutes' `Message` according to its `topic` and `event`.
        Socket-Channel has a 1-many relationship.
        Socket-Topic has a 1-many relationship.
        :param url: Websocket URL of the Realtime server. starts with `ws://` or `wss://`. Also accepts default Supabase URL: `http://` or `https://`
        :param params: Optional parameters for connection.
        :param hb_interval: WS connection is kept alive by sending a heartbeat message. Optional, defaults to 5.
        """
        self.url = f"{re.sub(r'https://', 'wss://', re.sub(r'http://', 'ws://', url, flags=re.IGNORECASE), flags=re.IGNORECASE)}/realtime/v1/websocket?apikey={token}"
        self.http_endpoint = http_endpoint_url(url)
        self.is_connected = False
        self.params = params

        self.apikey = token
        self.access_token = token

        self.hb_interval = hb_interval
        self.ws_connection: websockets.client.WebSocketClientProtocol
        self.kept_alive = False
        self.ref = 0
        self.auto_reconnect = auto_reconnect
        self.channels: Dict[str, Channel] = {}
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff

        self.access_token: Union[str, None] = token
        self._api_key = token

    @ensure_connection
    def listen(self) -> None:
        """
        Wrapper for async def _listen() to expose a non-async interface
        In most cases, this should be the last method executed as it starts an infinite listening loop.
        :return: None
        """
        asyncio.get_event_loop().run_until_complete(self.listen_async())

    @ensure_connection
    async def listen_async(self):
        await asyncio.gather(self._listen(), self._keep_alive())

    async def _listen(self) -> None:
        """
        An infinite loop that keeps listening.
        :return: None
        """
        while True:
            try:
                msg = await self.ws_connection.recv()
                msg = Message(**json.loads(msg))

                logging.info(f"receive: {msg}")
                channel = self.channels.get(msg.topic)

                if channel is None:
                    logging.info(f"Channel {msg.topic} not found")
                    continue

                for cl in channel.listeners:
                    if cl.event == msg.event:
                        cl.callback(msg.payload)

            except websockets.exceptions.ConnectionClosed:
                if self.auto_reconnect:
                    logging.info(
                        "Connection with server closed, trying to reconnect..."
                    )
                    await self._connect()
                    for topic, channel in self.channels.items():
                        await channel.join()
                else:
                    logging.exception("Connection with the server closed.")
                    break

    def connect(self) -> None:
        """
        Wrapper for async def _connect() to expose a non-async interface
        """

        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._connect())
        self.is_connected = True

    async def _connect(self) -> None:
        retries = 0
        backoff = self.initial_backoff

        while retries < self.max_retries:
            try:
                ws_connection = await websockets.connect(self.url)
                if ws_connection.open:
                    logging.info("Connection was successful")
                    self.ws_connection = ws_connection
                    self.is_connected = True
                    return
                else:
                    raise Exception("Failed to open WebSocket connection")
            except Exception as e:
                retries += 1
                if retries >= self.max_retries or not self.auto_reconnect:
                    logging.error(
                        f"Failed to establish WebSocket connection after {retries} attempts: {e}"
                    )
                    raise
                else:
                    wait_time = backoff * (2 ** (retries - 1))  # Exponential backoff
                    logging.info(
                        f"Connection attempt {retries} failed. Retrying in {wait_time:.2f} seconds..."
                    )
                    await asyncio.sleep(wait_time)
                    backoff = min(backoff * 2, 60)  # Cap the backoff at 60 seconds

        raise Exception(
            f"Failed to establish WebSocket connection after {self.max_retries} attempts"
        )

    @ensure_connection
    def close(self) -> None:
        """
        Wrapper for async def _close() to expose a non-async interface
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._close())
        self.is_connected = False

    async def _close(self) -> None:
        await self.ws_connection.close()

    async def _keep_alive(self) -> None:
        """
        Sending heartbeat to server every 5 seconds
        Ping - pong messages to verify connection is alive
        """
        while True:
            try:
                data = dict(
                    topic=PHOENIX_CHANNEL,
                    event=ChannelEvents.heartbeat,
                    payload=HEARTBEAT_PAYLOAD,
                    ref=None,
                )
                await self._send(data)
                await asyncio.sleep(self.hb_interval)
            except websockets.exceptions.ConnectionClosed:
                if self.auto_reconnect:
                    logging.info(
                        "Connection with server closed, trying to reconnect..."
                    )
                    await self._connect()
                else:
                    logging.exception("Connection with the server closed.")
                    break

    @ensure_connection
    def set_channel(self, topic: str, channel_params: Dict[str, Any]) -> Channel:
        """
        :param topic: Initializes a channel and creates a two-way association with the socket
        :return: Channel
        """
        topic = f"realtime:{topic}"
        chan = Channel(self, topic, channel_params, self.params)
        self.channels[topic] = chan

        return chan

    def add_channel(self, channel: Channel) -> None:
        """
        Associates the given channel object with the socket.
        :param channel: Channel object to associate with the socket.
        :return: None
        """
        topic = channel.topic
        self.channels[topic] = channel

    def summary(self) -> None:
        """
        Prints a list of topics and event the socket is listening to
        :return: None
        """
        for topic, channel in self.channels.items():
            print(f"Topic: {topic} | Events: {[e for e, _ in channel.listeners]}]")

    @ensure_connection
    def set_auth(self, token: Union[str, None]) -> None:
        self.access_token = token

        for _, channel in self.channels.items():
            if channel.joined:
                channel._push(ChannelEvents.access_token, {"access_token": token})

    def _make_ref(self) -> str:
        self.ref += 1
        return f"{self.ref}"

    async def _send(self, message):
        logger.info(f"Sending: {message}")
        await self.ws_connection.send(json.dumps(message))

    def send(self, message):
        asyncio.get_event_loop().run_until_complete(self._send(message))
