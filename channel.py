from constants import ChannelEvents
import websockets
import asyncio
import json


class Channel:
    def __init__(self, socket, topic, params):
        self.socket = socket
        self.topic = topic
        self.params = params
        self.callbacks = []
        self.joined = False


    def join(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._join())
        print("joined")
        return self

    async def _join(self):
        join_req = dict(topic=self.topic, event="phx_join", payload={}, ref=None)

        try:
            await self.socket.ws_connection.send(json.dumps(join_req))

        except Exception as e:
            # TODO: this needs some work.
            # raise ChannelJoinFailure() from e
            pass


    def on(self, event: str, callback):

        # TODO: Should I return self so that I can allow chaining?
        self.callbacks.append((event, callback))



    def off(self, event: str):
        self.callbacks = [callback for callback in self.callbacks if callback[0] != event]
