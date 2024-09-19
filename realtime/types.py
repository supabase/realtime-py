from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Literal, Optional, TypeVar

from typing_extensions import Protocol, TypedDict

# Constants
DEFAULT_TIMEOUT: int = 10  # Default timeout in seconds for operations
PHOENIX_CHANNEL: str = (
    "phoenix"  # Reserved channel name for heartbeat and system messages
)

# Type variables and custom types
TCallback = TypeVar("TCallback", bound=Callable[..., Any])
TReturn = TypeVar("TReturn")
TPayload = TypeVar("TPayload", bound=Dict[str, Any])


# Callback Protocols
class EventCallback(Protocol):
    """Protocol defining the structure of an event callback."""

    async def __call__(self, payload: Dict[str, Any], ref: Optional[str]) -> None: ...


class PresenceOnJoinCallback(Protocol):
    """Protocol defining the structure for a presence join callback."""

    async def __call__(
        self, key: str, current_presences: List[Presence], new_presences: List[Presence]
    ) -> None: ...


class PresenceOnLeaveCallback(Protocol):
    """Protocol defining the structure for a presence leave callback."""

    async def __call__(
        self,
        key: str,
        current_presences: List[Presence],
        left_presences: List[Presence],
    ) -> None: ...


class SyncCallback(Protocol):
    """Protocol defining the structure for a presence sync callback."""

    async def __call__(self) -> None: ...


# Enums
class ChannelEvents(str, Enum):
    """Channel events as expected by the Phoenix server."""

    CLOSE = "phx_close"
    ERROR = "phx_error"
    JOIN = "phx_join"
    REPLY = "phx_reply"
    LEAVE = "phx_leave"
    AUTH = "phx_auth"
    HEARTBEAT = "heartbeat"
    ACCESS_TOKEN = "access_token"
    BROADCAST = "broadcast"
    PRESENCE = "presence"
    PRESENCE_STATE = "presence_state"
    PRESENCE_DIFF = "presence_diff"
    SYSTEM = "system"


class ChannelStates(str, Enum):
    """Possible states of a channel."""

    JOINED = "joined"
    CLOSED = "closed"
    ERRORED = "errored"
    JOINING = "joining"
    LEAVING = "leaving"
    LEFT = "left"


class RealtimeSubscribeStates(str, Enum):
    """States for subscription status."""

    SUBSCRIBED = "SUBSCRIBED"
    TIMED_OUT = "TIMED_OUT"
    CLOSED = "CLOSED"
    CHANNEL_ERROR = "CHANNEL_ERROR"


class RealtimePresenceEvents(str, Enum):
    """Events related to presence."""

    PRESENCE_STATE = "presence_state"
    PRESENCE_DIFF = "presence_diff"


# Literals
RealtimePostgresChangesListenEvent = Literal["*", "INSERT", "UPDATE", "DELETE"]


# Data Classes
@dataclass
class Binding:
    """Represents an event listener binding on a channel."""

    event_type: str
    callback: EventCallback
    filter: Dict[str, Any]
    binding_id: Optional[str] = None


@dataclass
class Hook:
    """Represents a callback associated with a specific status."""

    status: str
    callback: EventCallback


@dataclass
class Presence:
    """Represents a single presence metadata entry."""

    phx_ref: str
    phx_ref_prev: Optional[str]
    metadata: Dict[str, Any]


@dataclass
class PresenceState:
    """Represents the state of presences in the channel."""

    presences: Dict[str, List[Presence]]


@dataclass
class PresenceDiff:
    """Represents the difference in presence state."""

    joins: Dict[str, List[Presence]]
    leaves: Dict[str, List[Presence]]


# TypedDicts
class RealtimeChannelConfig(TypedDict, total=False):
    """Configuration options for a channel."""

    broadcast: Dict[str, Any]
    presence: Dict[str, Any]
    postgres_changes: List[Dict[str, Any]]
    access_token: Optional[str]


class PresenceEventsType(TypedDict, total=False):
    """Events for presence."""

    state: str
    diff: str
    auth: str


class PresenceOpts(TypedDict, total=False):
    """Options for presence."""

    events: PresenceEventsType


# Custom Types
PresenceStateType = Dict[str, List[Presence]]


class RealtimeChannelOptions(TypedDict):
    """Options for initializing a Realtime channel."""

    config: RealtimeChannelConfig
