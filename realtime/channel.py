from __future__ import annotations

import asyncio
import json
from typing import Any, List, Dict, TYPE_CHECKING, NamedTuple

from realtime.types import Callback

if TYPE_CHECKING:
    from realtime.connection import Socket


class CallbackListener(NamedTuple):
    """A tuple with `event` and `callback` """
    event: str
    on_params: Dict[str, Any]
    callback: Callback


class Channel:
    """
    `Channel` is an abstraction for a topic listener for an existing socket connection.
    Each Channel has its own topic and a list of event-callbacks that responds to messages.
    Should only be instantiated through `connection.Socket().set_channel(topic)`
    Topic-Channel has a 1-many relationship.
    """

    def __init__(self, socket: Socket, topic: str, channel_params: Dict[str, Any] = {}, params = {}) -> None:
        """
        :param socket: Socket object
        :param topic: Topic that it subscribes to on the realtime server
        :param params:
        """
        self.socket = socket
        self.params = params
        self.channel_params = channel_params
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
        join_req = {
            "topic": self.topic,
            "event": "phx_join",
            "payload": {"config": self.channel_params},
            "ref": None
        }

        try:
            await self.socket.ws_connection.send(json.dumps(join_req))
        except Exception as e:
            print(str(e))  # TODO: better error propagation
            return

    def on(self, event: str, on_params: Dict[str, Any], callback: Callback) -> Channel:
        """
        :param event: A specific event will have a specific callback
        :param callback: Callback that takes msg payload as its first argument
        :return: Channel
        """
        if event == "presence":
            cl_diff = CallbackListener(event="presence_diff", on_params = on_params, callback=callback)
            cl_state = CallbackListener(event="presence_state", on_params = on_params, callback=callback)
            self.listeners.append(cl_diff)
            self.listeners.append(cl_state)
        else:
            cl = CallbackListener(event=event, on_params = on_params, callback=callback)
            self.listeners.append(cl)

        return self

    def off(self, event: str) -> None:
        """
        :param event: Stop responding to a certain event
        :return: None
        """
        self.listeners = [
            callback for callback in self.listeners if callback.event != event]
