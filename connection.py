import json
import websockets
from channel import Channel
from collections import defaultdict
import asyncio
from messages import Message, ChannelEvents, PHOENIX_CHANNEL, HEARTBEAT_PAYLOAD

class Socket:

    def __init__(self, url: str, params: dict = {}, hb_interval: int = 5):
        self.url = url
        self.channels = defaultdict(list)
        self.connected = False
        self.params: dict= params
        self.hb_interval: int = hb_interval
        self.ws_connection: websockets.client.WebSocketClientProtocol = None
        self.kept_alive = False


    def listen(self):

        loop = asyncio.get_event_loop()
        loop.run_until_complete(asyncio.gather(self._listen(), self._keep_alive()))


    async def _listen(self):
        while True:
            try:
                msg = await self.ws_connection.recv()
                # TODO: Load msg into some class with expected schema
                msg = Message(**json.loads(msg))
                if msg.event== ChannelEvents.reply:
                    continue
                # TODO: use a named tuple?
                for channel in self.channels.get(msg.topic, []):
                    for event, callback in channel.callbacks:
                        if event == msg.event:
                            callback(msg.payload)

            except websockets.exceptions.ConnectionClosed:
                print('Connection Closed')
                break


    def connect(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._connect())


    async def _connect(self):
        ws_connection = await websockets.connect(self.url)
        if ws_connection.open:
            # TODO: Include a logger to indicate successful connection
            print(type(ws_connection))
            self.ws_connection = ws_connection
            self.connected = True

        else:
            raise Exception("Connection Failed")

    async def _keep_alive(self):
        '''
        Sending heartbeat to server every 5 seconds
        Ping - pong messages to verify connection is alive
        '''
        if self.kept_alive:
            return

        else:
            self.kept_alive = True

        while True:
            try:
                data = dict(topic=PHOENIX_CHANNEL, event=ChannelEvents.heartbeat, payload=HEARTBEAT_PAYLOAD, ref=None)
                await self.ws_connection.send(json.dumps(data))
                await asyncio.sleep(self.hb_interval)
            except websockets.exceptions.ConnectionClosed:
                # TODO: use logger instead
                print('Connection with server closed')
                break

    def set_channel(self, topic: str):
        chan = Channel(self, topic, self.params)
        self.channels[topic].append(chan)

        return chan

    # TODO: Implement this to show summary to subscriptions
    def summary(self):
        # print a summary of subscriptions from the socket
            for topic, chans in self.channels.items():
                for chan in chans:
                    print(f"Topic: {topic} | Events: {[e for e, _ in chan.callbacks]}]")


