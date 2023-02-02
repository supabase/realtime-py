from collections import defaultdict
from functools import wraps
from typing import Any, Callable, List, Dict, cast, TypeVar, TYPE_CHECKING, NamedTuple
from typing_extensions import ParamSpec
from types import Callback
from exceptions import NotConnectedError
from message import HEARTBEAT_PAYLOAD, PHOENIX_CHANNEL, ChannelEvents, Message
from mongo_client import MongoServer
from datetime import datetime 
import requests
import json
import websockets
import asyncio
import logging
import time

db = MongoServer()


T_Retval = TypeVar("T_Retval")
T_ParamSpec = ParamSpec("T_ParamSpec")

logging.basicConfig(
    format="%(asctime)s:%(levelname)s - %(message)s", level=logging.INFO)

def ensure_connection(func: Callable[T_ParamSpec, T_Retval]):
    @wraps(func)
    def wrapper(*args: T_ParamSpec.args, **kwargs: T_ParamSpec.kwargs) -> T_Retval:
        if not args[0].connected:
            raise NotConnectedError(func.__name__)

        return func(*args, **kwargs)
        
    return wrapper

class Socket:
    def __init__(self, url: str, params: Dict[str, Any] = {}, hb_interval: int = 5) -> None:
        """
        `Socket` is the abstraction for an actual socket connection that receives and 'reroutes' `Message` according to its `topic` and `event`.
        Socket-Channel has a 1-many relationship.
        Socket-Topic has a 1-many relationship.
        :param url: Websocket URL of the Realtime server. starts with `ws://` or `wss://`
        :param params: Optional parameters for connection.
        :param hb_interval: WS connection is kept alive by sending a heartbeat message. Optional, defaults to 5.
        """
        self.url = url
        self.channels = defaultdict(list)
        self.connected = False
        self.params = params
        self.hb_interval = hb_interval
        self.ws_connection: websockets.client.WebSocketClientProtocol
        self.kept_alive = False
        self.restart = False
        self.done = False
        self.channels = cast(defaultdict[str, List[Channel]], self.channels)
        self.closedCount = 0

    @ensure_connection
    def listen(self) -> None:
        """
        Wrapper for async def _listen() to expose a non-async interface
        In most cases, this should be the last method executed as it starts an infinite listening loop.
        :return: None
        """
        self.restart = False
        self.done = False
        loop = asyncio.get_event_loop()  # TODO: replace with get_running_loop
        print('waiting til complete')
        loop.run_until_complete(asyncio.gather(
            self._listen(), self._keep_alive(), self._manageChannels()))


    async def _listen(self) -> None:
        """
        An infinite loop that keeps listening.
        :return: None
        """
        breakIt = 0
        while breakIt != 1:
            try:
                msg = "never obtained"
                msg = await self.ws_connection.recv()
                msg = Message(**json.loads(msg))

                if msg.event == ChannelEvents.reply:
                    if len(self.ws_connection.messages) == 0  and self.done == True:
                        breakIt = 1
                    else:
                        continue
                for channel in self.channels.get(msg.topic, []):
                    for cl in channel.listeners:
                        if cl.event == msg.event:
                            cl.callback(msg.payload)
            except websockets.exceptions.ConnectionClosed:
                self.restart = True
                print("_listen FAILED")
                print(msg)
                logging.exception("Connection closed")
                break

    def connect(self) -> None:
        """
        Wrapper for async def _connect() to expose a non-async interface
        """
        loop = asyncio.get_event_loop()  # TODO: replace with get_running
        loop.run_until_complete(self._connect())
        self.connected = True

    async def _connect(self) -> None:
        while self.connected == False:
            connectFailed = 0
            try:
                ws_connection = await websockets.connect(self.url)
            except:
                print("await connect Failed")
                connectFailed = 1
            if connectFailed == 0:    
                if not ws_connection.open:
                    raise Exception("Connection Failed")
                logging.info("Connection was successful")
                self.ws_connection = ws_connection
                self.connected = True
                time.sleep(1)
            elif self.connected == False:
                print('Waiting 5 to retry connection')
                time.sleep(5)

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
                try:
                    await self.ws_connection.send(json.dumps(data))
                except websockets.exceptions.ConnectionClosed:
                    logging.exception("Connection with server closed")
                    self.restart = True
                    self.done = True
                    print("_keep_alive FAILED")
                    print(f'Restart = {self.restart}, Done: {self.done}')
                    break
                if self.restart:
                    self.done = True
                    break
                await asyncio.sleep(self.hb_interval)
            except websockets.exceptions.ConnectionClosed:
                logging.exception("Connection with server closed")
                self.restart = True
                self.done = True
                print("_keep_alive FAILED")
                print(f'Restart = {self.restart}, Done: {self.done}')
                break

    async def _manageChannels(self) -> None:
        await asyncio.sleep(5)
        i=0
        localBreak = 0
        while self.restart != True and localBreak != 1:
            await asyncio.sleep(1)
            collectionsToWatch = db.getCollectionsToListen()
            #print(collectionsToWatch)
            for collection in collectionsToWatch:
                if str(collection) not in str(self.channels):
                    self.restart = True
                    localBreak = 1
                    break

    @ensure_connection
    def set_channel(self, topic: str):
        """
        :param topic: Initializes a channel and creates a two-way association with the socket
        :return: Channel
        """
        chan = Channel(self, topic, self.params)
        self.channels[topic].append(chan)

        return chan

    def summary(self) -> None:
        """
        Prints a list of topics and event the socket is listening to
        :return: None
        """
        for topic, chans in self.channels.items():
            for chan in chans:
                print(
                    f"Topic: {topic} | Events: {[e for e, _ in chan.callbacks]}]")

class CallbackListener(NamedTuple):
    """A tuple with `event` and `callback` """
    event: str
    callback: Callback


class Channel:
    """
    `Channel` is an abstraction for a topic listener for an existing socket connection.
    Each Channel has its own topic and a list of event-callbacks that responds to messages.
    Should only be instantiated through `connection.Socket().set_channel(topic)`
    Topic-Channel has a 1-many relationship.
    """

    def __init__(self, socket: Socket, topic: str, params: Dict[str, Any] = {}) -> None:
        """
        :param socket: Socket object
        :param topic: Topic that it subscribes to on the realtime server
        :param params:
        """
        self.socket = socket
        self.params = params
        self.topic = topic
        self.listeners: List[CallbackListener] = []
        self.joined = False
        time.sleep(0.001)
        self.reference = int((time.time() - 1671063199)*10000)

    def join(self):
        """
        Wrapper for async def _join() to expose a non-async interface
        Essentially gets the only event loop and attempt joining a topic
        :return: Channel
        """
        loop = asyncio.get_event_loop()  # TODO: replace with get_running_loop
        loop.run_until_complete(self._join())
        return self

    async def _join(self) -> None:
        """
        Coroutine that attempts to join Phoenix Realtime server via a certain topic
        :return: None
        """
        join_req = dict(topic=self.topic, event="phx_join",
                        payload={}, ref=self.reference)
        print(join_req)

        try:
            await self.socket.ws_connection.send(json.dumps(join_req))
        except Exception as e:
            print(e)
            return

    def leave(self):
        """
        Wrapper for async def _join() to expose a non-async interface
        Essentially gets the only event loop and attempt joining a topic
        :return: Channel
        """
        loop = asyncio.get_running_loop()  # TODO: replace with get_running_loop
        loop.run_until_complete(self._leave())
        return self

    async def _leave(self) -> None:
        """
        Coroutine that attempts to join Phoenix Realtime server via a certain topic
        :return: None
        """
        leave_req = dict(topic=self.topic, event="phx_leave",
                        payload={}, ref=self.reference)

        try:
            await self.socket.ws_connection.send(json.dumps(leave_req))
        except Exception as e:
            print(e)
            return

    def on(self, event: str, callback: Callback):
        """
        :param event: A specific event will have a specific callback
        :param callback: Callback that takes msg payload as its first argument
        :return: Channel
        """
        cl = CallbackListener(event=event, callback=callback)
        self.listeners.append(cl)
        return self

    def off(self, event: str) -> None:
        """
        :param event: Stop responding to a certain event
        :return: None
        """
        self.listeners = [
            callback for callback in self.listeners if callback.event != event]