from enum import Enum
from dataclasses import dataclass

@dataclass
class Message:
    event: str
    payload: dict
    ref: any
    topic: str

    def __hash__(self):
        return hash((self.event, tuple(list(self.payload.values())), self.ref, self.topic))


class ChannelEvents(str, Enum):
    close = "phx_close"
    error = "phx_error"
    join = "phx_join"
    reply = "phx_reply"
    leave = "phx_leave"
    heartbeat = "heartbeat"


PHOENIX_CHANNEL = "phoenix"
HEARTBEAT_PAYLOAD = {"msg": "ping"}
