import logging

# Configure the root logger for the module
logging.getLogger(__name__).addHandler(logging.NullHandler())

from realtime._async.channel import AsyncRealtimeChannel
from realtime._async.client import AsyncRealtimeClient
from realtime._async.presence import AsyncRealtimePresence
from realtime._sync.client import SyncRealtimeChannel, SyncRealtimeClient
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
    "ChannelEvents",
    "ChannelStates",
    "RealtimeSubscribeStates",
    "RealtimePresenceEvents",
    "RealtimePostgresChangesListenEvent",
    "RealtimeChannelOptions",
    "RealtimeError",
    "NotConnectedError",
    "AuthorizationError",
    "ConnectionFailedError",
    "ReconnectionFailedError",
    "InvalidMessageError",
    "SyncRealtimeClient",
    "SyncRealtimeChannel",
    "Presence",
    "__version__",
]
