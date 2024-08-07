import asyncio
import json
from typing import Any, Dict
from realtime.channel import Channel
import logging

class Push:
    def __init__(self, channel: Channel, event: str, payload: Dict[str, Any] = {}):
        self.channel = channel
        self.event = event
        self.payload = payload
        self.ref = ""

    
    def send(self):
        asyncio.get_event_loop().run_until_complete(self._send())
        
    async def _send(self):
        self.ref = self.channel.socket._make_ref()

        message = {
            "topic": self.channel.topic,
            "event": self.event,
            "payload": self.payload,
            "ref": self.ref,
        }

        try:
            await self.socket.ws_connection.send(json.dumps(message))
        except Exception as e:
            logging.error(f"send push failed: {e}")



    def update_payload(self, payload: Dict[str, Any]):
        self.payload = { **self.payload, **payload }