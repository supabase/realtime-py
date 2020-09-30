import asyncio
import json
from typing import List
from collections import namedtuple

CallbackListener = namedtuple("CallbackListener", "event callback")


class Channel:
    def __init__(self, socket, topic: str, params: dict):
        self.socket = socket
        self.topic: str = topic
        self.params: dict = params
        self.listeners: List[CallbackListener] = []
        self.joined: bool = False

    def join(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._join())
        return self

    async def _join(self):
        join_req = dict(topic=self.topic, event="phx_join", payload={}, ref=None)

        try:
            await self.socket.ws_connection.send(json.dumps(join_req))

        except Exception as e:
            print(str(e))
            return

    def on(self, event: str, callback):

        # TODO: Should I return self so that I can allow chaining?
        cl = CallbackListener(event=event, callback=callback)
        self.listeners.append(cl)

    def off(self, event: str):
        self.listeners = [callback for callback in self.listeners if callback.event != event]
