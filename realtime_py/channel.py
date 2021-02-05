import asyncio
import json
from collections import namedtuple
from typing import List

"""
Callback Listener is a tuple with `event` and `callback` 
"""
CallbackListener = namedtuple("CallbackListener", "event callback")


class Channel:
    """
    `Channel` is an abstraction for a topic listener for an existing socket connection.
    Each Channel has its own topic and a list of event-callbacks that responds to messages.
    Should only be instantiated through `connection.Socket().set_chanel(topic)`
    Topic-Channel has a 1-many relationship.
    """

    def __init__(self, socket, topic: str, params: dict = {}):
        """
        :param socket: Socket object
        :param topic: Topic that it subscribes to on the realtime server
        :param params:
        """
        self.socket = socket
        self.topic: str = topic
        self.params: dict = params
        self.listeners: List[CallbackListener] = []
        self.joined: bool = False

    def join(self):
        """
        Wrapper for async def _join() to expose a non-async interface
        Essentially gets the only event loop and attempt joining a topic
        :return: None
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._join())
        return self

    async def _join(self):
        """
        Coroutine that attempts to join Phoenix Realtime server via a certain topic
        :return: Channel.channel
        """
        join_req = dict(topic=self.topic, event="phx_join", payload={}, ref=None)

        try:
            await self.socket.ws_connection.send(json.dumps(join_req))

        except Exception as e:
            print(str(e))
            return

    def on(self, event: str, callback):
        """
        :param event: A specific event will have a specific callback
        :param callback: Callback that takes msg payload as its first argument
        :return: None
        """

        cl = CallbackListener(event=event, callback=callback)
        self.listeners.append(cl)
        return self

    def off(self, event: str):
        """
        :param event: Stop responding to a certain event
        :return: None
        """
        self.listeners = [callback for callback in self.listeners if callback.event != event]
