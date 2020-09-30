from enum import Enum
from dataclasses import dataclass
from typing import Any


@dataclass
class Message:
    event: str
    payload: dict
    ref: any
    topic: str

    def __hash__(self):
        return hash((self.event, tuple(list(self.payload.values())), self.ref, self.topic))
    #
    # def __init__(self, msg: dict):
    #     self.event = msg["event"]
    #     self.payload = msg["payload"]
    #     self.ref = msg["ref"]
    #     self.topic = msg["topic"]


class ChannelEvents(str, Enum):
    close = "phx_close"
    error = "phx_error"
    join = "phx_join"
    reply = "phx_reply"
    leave = "phx_leave"
    heartbeat = "heartbeat"


PHOENIX_CHANNEL = "phoenix"
HEARTBEAT_PAYLOAD = {"msg": "ping"}
