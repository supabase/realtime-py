from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar

from typing_extensions import ParamSpec

T_ParamSpec = ParamSpec("T_ParamSpec")
T_Retval = TypeVar("T_Retval")

# Custom types
Callback = Callable[T_ParamSpec, T_Retval]

DEFAULT_TIMEOUT = 10000
DEFAULT_HEADERS = {}
VSN = "1.0.0"

# Define a type alias for WebSocketLikeConstructor
WebSocketLikeConstructor = Callable[..., Any]
Fetch = Callable[..., Any]


class RealtimeClientOptions:
    def __init__(
        self,
        transport: Optional[WebSocketLikeConstructor] = None,
        timeout: Optional[int] = None,
        heartbeat_interval_ms: Optional[int] = None,
        logger: Optional[Callable] = None,
        encode: Optional[Callable] = None,
        decode: Optional[Callable] = None,
        reconnect_after_ms: Optional[Callable[[int], int]] = None,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        log_level: Optional[str] = None,
        fetch: Optional[Fetch] = None,
    ):
        self.transport = transport
        self.timeout = timeout
        self.heartbeat_interval_ms = heartbeat_interval_ms
        self.logger = logger
        self.encode = encode
        self.decode = decode
        self.reconnect_after_ms = reconnect_after_ms
        self.headers = headers if headers is not None else {}
        self.params = params if params is not None else {}
        self.log_level = log_level
        self.fetch = fetch


class PushStatus(str, Enum):
    OK = "ok"
    TIMED_OUT = "timed_out"
    ERROR = "error"


class ChannelState(str, Enum):
    CLOSED = "closed"
    ERRORED = "errored"
    JOINED = "joined"
    JOINING = "joining"
    LEAVING = "leaving"


class ConnectionState(str, Enum):
    CONNECTING = "connecting"
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
