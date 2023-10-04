from __future__ import annotations

import asyncio
import json
from typing import Any, List, Dict, TYPE_CHECKING, NamedTuple
from realtime.message import *

from realtime.types import Callback

if TYPE_CHECKING:
    from realtime.connection import Socket


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

    def join(self) -> Channel:
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
        if self.socket.version == 1:
            join_req = dict(topic=self.topic, event=ChannelEvents.join,
                        payload={}, ref=None)
        elif self.socket.version == 2:
            join_req = [None, None, self.topic, ChannelEvents.join, {}]

        try:
            await self.socket.ws_connection.send(json.dumps(join_req))
        except Exception as e:
            print(str(e))  # TODO: better error propagation
            return

    def leave(self) -> Channel:
        """
        Wrapper for async def _leave() to expose a non-async interface
        Essentially gets the only event loop and attempt leaving a topic
        :return: Channel
        """
        loop = asyncio.get_event_loop()  # TODO: replace with get_running_loop
        loop.run_until_complete(self._join())
        return self

    async def _leave(self) -> None:
        """
        Coroutine that attempts to join Phoenix Realtime server via a certain topic
        :return: None
        """
        if self.socket.version == 1:
            join_req = dict(topic=self.topic, event=ChannelEvents.leave,
                        payload={}, ref=None)
        elif self.socket.version == 2:
            join_req = [None, None, self.topic, ChannelEvents.leave, {}]

        try:
            await self.socket.ws_connection.send(json.dumps(join_req))
        except Exception as e:
            print(str(e))  # TODO: better error propagation
            return

    def on(self, event: str, callback: Callback) -> Channel:
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

    def send(self, event_name: str, payload:str) -> None:
        """
        Wrapper for async def _send() to expose a non-async interface
        Essentially gets the only event loop and attempt sending a payload
        to a topic
        :param event_name: The event_name: it must match the first argument of a handle_in function on the server channel module.
        :param payload: The payload to be sent to the phoenix server
        :return: None
        """
        loop = asyncio.get_event_loop()  # TODO: replace with get_running_loop
        loop.run_until_complete(self._send(event_name, payload))
        return self

    async def _send(self, event_name: str, payload:str) -> None:
        """
        Coroutine that attempts to join Phoenix Realtime server via a certain topic
        :param event_name: The event_name: it must match the first argument of a handle_in function on the server channel module.
        :param payload: The payload to be sent to the phoenix server
        :return: None
        """
        if self.socket.version == 1:
            msg = dict(topic=self.topic, event=event_name,
                        payload=payload, ref=None)
        elif self.socket.version == 2:
            msg = [3, 3, self.topic, event_name, payload]

        try:
            await self.socket.ws_connection.send(json.dumps(msg))
        except Exception as e:
            print(str(e))  # TODO: better error propagation
            return
