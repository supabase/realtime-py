from enum import Enum
from typing import Callable, TypeVar

from typing_extensions import ParamSpec

T_ParamSpec = ParamSpec("T_ParamSpec")
T_Retval = TypeVar("T_Retval")

# Custom types
Callback = Callable[T_ParamSpec, T_Retval]


DEFAULT_TIMEOUT = 10
PHOENIX_CHANNEL = "phoenix"


class ChannelEvents(str, Enum):
    """
    ChannelEvents are a bunch of constant strings that are defined according to
    what the Phoenix realtime server expects.
    """

    close = "phx_close"
    error = "phx_error"
    join = "phx_join"
    reply = "phx_reply"
    leave = "phx_leave"
    heartbeat = "heartbeat"
    access_token = "access_token"
    broadcast = "broadcast"
    presence = "presence"


class ChannelStates(str, Enum):
    JOINED = "joined"
    CLOSED = "closed"
    ERRORED = "errored"
    JOINING = "joining"
    LEAVING = "leaving"
