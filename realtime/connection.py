import asyncio
import json
import logging
import re
from collections import defaultdict
from functools import wraps
from typing import Any, DefaultDict, Dict, List

import websockets

from realtime.channel import Channel
from realtime.exceptions import NotConnectedError
from realtime.message import HEARTBEAT_PAYLOAD, PHOENIX_CHANNEL, ChannelEvents, Message
from realtime.types import Callback, T_ParamSpec, T_Retval

logging.basicConfig(
    format="%(asctime)s:%(levelname)s - %(message)s", level=logging.INFO
)


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
    ) -> None:
        """
        `Socket` is the abstraction for an actual socket connection that receives and 'reroutes' `Message` according to its `topic` and `event`.
        Socket-Channel has a 1-many relationship.
        Socket-Topic has a 1-many relationship.
        :param url: Websocket URL of the Realtime server. starts with `ws://` or `wss://`. Also accepts default Supabase URL: `http://` or `https://`
        :param params: Optional parameters for connection.
        :param hb_interval: WS connection is kept alive by sending a heartbeat message. Optional, defaults to 5.
        """
        self.url = f"{re.sub(r'https?://', 'wss://', url, flags=re.IGNORECASE)}/realtime/v1/websocket?apikey={token}"
        self.channels = defaultdict(list)
        self.is_connected = False
        self.params = params
        self.hb_interval = hb_interval
        self.ws_connection: websockets.client.WebSocketClientProtocol
        self.kept_alive = False
        self.auto_reconnect = auto_reconnect

        self.channels: DefaultDict[str, List[Channel]] = defaultdict(list)

    @ensure_connection
    def listen(self) -> None:
        """
        Wrapper for async def _listen() to expose a non-async interface
        In most cases, this should be the last method executed as it starts an infinite listening loop.
        :return: None
        """
        loop = asyncio.get_event_loop()  # TODO: replace with get_running_loop
        loop.run_until_complete(asyncio.gather(self._listen(), self._keep_alive()))

    async def _listen(self) -> None:
        """
        An infinite loop that keeps listening.
        :return: None
        """
        while True:
            try:
                msg = await self.ws_connection.recv()
                msg = Message(**json.loads(msg))
                for channel in self.channels.get(msg.topic, []):
                    for cl in channel.listeners:
                        if cl.event == msg.event:
                            if cl.event in ["presence_diff", "presence_state"]:
                                cl.callback(msg.payload)
                                continue
                            if cl.event in ["postgres_changes"]:
                                cl.callback(msg.payload)
                                continue
                            if cl.on_params["event"] in [msg.payload["event"], "*"]:
                                cl.callback(msg.payload)
            except websockets.exceptions.ConnectionClosed:
                if self.auto_reconnect:
                    logging.info(
                        "Connection with server closed, trying to reconnect..."
                    )
                    await self._connect()
                    for topic, channels in self.channels.items():
                        for channel in channels:
                            await channel._join()
                else:
                    logging.exception("Connection with the server closed.")
                    break

    def connect(self) -> None:
        """
        Wrapper for async def _connect() to expose a non-async interface
        """

        loop = asyncio.get_event_loop()  # TODO: replace with get_running
        loop.run_until_complete(self._connect())
        self.is_connected = True

    async def _connect(self) -> None:
        try:
            ws_connection = await websockets.connect(self.url)
        except Exception as e:
            logging.error(f"Failed to establish WebSocket connection: {e}")
            if self.auto_reconnect:
                logging.info("Retrying connection...")
                await asyncio.sleep(5)  # Wait before retrying
                await self._connect()   # Retry connection
            else:
                raise

        if ws_connection.open:
            logging.info("Connection was successful")
            self.ws_connection = ws_connection
            self.is_connected = True
        else:
            raise Exception("Failed to open WebSocket connection")

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
                await self.ws_connection.send(json.dumps(data))
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
        self.channels[topic].append(chan)

        return chan

    def set_channel(self, channel: Channel) -> None:
        """
        Associates the given channel object with the socket.
        :param channel: Channel object to associate with the socket.
        :return: None
        """
        topic = channel.topic
        self.channels[topic].append(channel)

    def summary(self) -> None:
        """
        Prints a list of topics and event the socket is listening to
        :return: None
        """
        for topic, chans in self.channels.items():
            for chan in chans:
                print(f"Topic: {topic} | Events: {[e for e, _ in chan.callbacks]}]")
