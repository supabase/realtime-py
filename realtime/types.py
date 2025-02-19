from enum import Enum
from typing import Any, Callable, Dict, List, Literal, Optional, TypedDict, TypeVar

from typing_extensions import ParamSpec

# Constants
DEFAULT_TIMEOUT = 10
PHOENIX_CHANNEL = "phoenix"
VSN = "1.0.0"
DEFAULT_HEARTBEAT_INTERVAL = 25

# Type variables and custom types
T_ParamSpec = ParamSpec("T_ParamSpec")
T_Retval = TypeVar("T_Retval")
Callback = Callable[T_ParamSpec, T_Retval]


# Enums
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


class RealtimeSubscribeStates(str, Enum):
    SUBSCRIBED = "SUBSCRIBED"
    TIMED_OUT = "TIMED_OUT"
    CLOSED = "CLOSED"
    CHANNEL_ERROR = "CHANNEL_ERROR"


class RealtimePresenceListenEvents(str, Enum):
    SYNC = "SYNC"
    JOIN = "JOIN"
    LEAVE = "LEAVE"


# Literals
RealtimePostgresChangesListenEvent = Literal["*", "INSERT", "UPDATE", "DELETE"]


# Classes
class Binding:
    def __init__(
        self,
        type: str,
        filter: Dict[str, Any],
        callback: Callback,
        id: Optional[str] = None,
    ):
        self.type = type
        self.filter = filter
        self.callback = callback
        self.id = id


class _Hook:
    def __init__(self, status: str, callback: Callback):
        self.status = status
        self.callback = callback


class Presence(Dict[str, Any]):
    presence_ref: str


class PresenceEvents:
    def __init__(self, state: str, diff: str):
        self.state = state
        self.diff = diff


class PresenceOpts:
    def __init__(self, events: PresenceEvents):
        self.events = events


# TypedDicts
class RealtimeChannelBroadcastConfig(TypedDict):
    ack: bool
    self: bool


class RealtimeChannelPresenceConfig(TypedDict):
    key: str


class RealtimeChannelConfig(TypedDict):
    broadcast: RealtimeChannelBroadcastConfig
    presence: RealtimeChannelPresenceConfig
    private: bool


class RealtimeChannelOptions(TypedDict):
    config: RealtimeChannelConfig


class PresenceMeta(TypedDict, total=False):
    phx_ref: str
    phx_ref_prev: str


class RawPresenceStateEntry(TypedDict):
    metas: List[PresenceMeta]


# Custom types
PresenceOnJoinCallback = Callable[[str, List[Any], List[Any]], None]
PresenceOnLeaveCallback = Callable[[str, List[Any], List[Any]], None]
RealtimePresenceState = Dict[str, List[Presence]]
RawPresenceState = Dict[str, RawPresenceStateEntry]


class RawPresenceDiff(TypedDict):
    joins: RawPresenceState
    leaves: RawPresenceState


class PresenceDiff(TypedDict):
    joins: RealtimePresenceState
    leaves: RealtimePresenceState


# Specific payload types
class RealtimePresenceJoinPayload(Dict[str, Any]):
    event: Literal[RealtimePresenceListenEvents.JOIN]
    key: str
    current_presences: List[Presence]
    new_presences: List[Presence]


class RealtimePresenceLeavePayload(Dict[str, Any]):
    event: Literal[RealtimePresenceListenEvents.LEAVE]
    key: str
    current_presences: List[Presence]
    left_presences: List[Presence]
