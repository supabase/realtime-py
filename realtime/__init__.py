import logging

# Configure the root logger for the module
logging.getLogger(__name__).addHandler(logging.NullHandler())

from realtime._async.channel import AsyncRealtimeChannel
from realtime._async.client import AsyncRealtimeClient
from realtime._async.presence import AsyncRealtimePresence
from realtime._sync.channel import SyncRealtimeChannel
from realtime._sync.client import SyncRealtimeClient
from realtime.exceptions import (
    AuthorizationError,
    ConnectionFailedError,
    InvalidMessageError,
    NotConnectedError,
    RealtimeError,
    ReconnectionFailedError,
)
from realtime.types import (
    ChannelEvents,
    ChannelStates,
    Presence,
    PresenceOnJoinCallback,
    PresenceOnLeaveCallback,
    RealtimeChannelOptions,
    RealtimePostgresChangesListenEvent,
    RealtimePresenceEvents,
    RealtimeSubscribeStates,
)
from realtime.version import __version__

__all__ = [
    "AsyncRealtimeClient",
    "AsyncRealtimeChannel",
    "AsyncRealtimePresence",
    "SyncRealtimeClient",
    "SyncRealtimeChannel",
    "ChannelEvents",
    "ChannelStates",
    "RealtimeSubscribeStates",
    "RealtimePresenceEvents",
    "RealtimePostgresChangesListenEvent",
    "RealtimeChannelOptions",
    "Presence",
    "PresenceOnJoinCallback",
    "PresenceOnLeaveCallback",
    "RealtimeError",
    "NotConnectedError",
    "AuthorizationError",
    "ConnectionFailedError",
    "ReconnectionFailedError",
    "InvalidMessageError",
    "__version__",
]
