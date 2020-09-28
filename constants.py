from enum import Enum


class ChannelEvents(str, Enum):
    close = "phx_close"
    error = "phx_error"
    join = "phx_join"
    reply = "phx_reply"
    leave = "phx_leave"
    heartbeat = "heartbeat"


PHOENIX_CHANNEL = "phoenix"
HEARTBEAT_PAYLOAD = {"msg": "ping"}