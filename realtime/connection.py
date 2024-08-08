import asyncio
import json
import logging
import re
from functools import wraps
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import websockets
from websockets.frames import CloseCode
from websockets.protocol import State

from realtime.exceptions import NotConnectedError
from realtime.message import ChannelEvents
from realtime.types import (
    DEFAULT_HEADERS,
    DEFAULT_TIMEOUT,
    VSN,
    Callback,
    ConnectionState,
    RealtimeClientOptions,
    T_ParamSpec,
    T_Retval,
)

logging.basicConfig(
    format="%(asctime)s:%(levelname)s - %(message)s", level=logging.DEBUG
)

logger = logging.getLogger(__name__)


def ensure_connection(func: Callback):
    @wraps(func)
    def wrapper(*args: T_ParamSpec.args, **kwargs: T_ParamSpec.kwargs) -> T_Retval:
        if not args[0].is_connected:
            raise NotConnectedError(func.__name__)

        return func(*args, **kwargs)

    return wrapper


class Timer:
    def __init__(self, callback: Callable[[], None], timeout: int):
        self.callback: Callable[[], None] = callback
        self.timeout: int = timeout
        self.timer: Optional[asyncio.TimerHandle] = None

    def reset(self) -> None:
        if self.timer:
            self.timer.cancel()
        self.timer = asyncio.get_event_loop().call_later(self.timeout, self.callback)

    def schedule_timeout(self) -> None:
        self.reset()


class Serializer:
    def decode(self, raw_message: str) -> Dict[str, Any]:
        return json.loads(raw_message)

    def encode(self, payload: Dict[str, Any]) -> str:
        return json.dumps(payload)


class Socket:
    def __init__(
        self, endpoint: str, options: RealtimeClientOptions = RealtimeClientOptions()
    ):
        self.endpoint: str = f"{endpoint}/websocket"
        self.http_endpoint: str = self._http_endpoint_url(endpoint)
        self.timeout = options.timeout or DEFAULT_TIMEOUT
        self.params: Dict[str, str] = options.params or {}
        self.headers: Dict[str, str] = {
            **DEFAULT_HEADERS,
            **(options.headers or {}),
        }
        self.heartbeat_interval_ms: int = options.heartbeat_interval_ms or 30000
        self.logger: Callable = self._noop  # options.get('logger', self._noop)
        self.encode: Callable[[Dict[str, Any], Callable[[str], None]], None] = (
            self._default_encode
        )  # options.get('encode', self._default_encode)
        self.decode: Callable[[str], Dict[str, Any]] = (
            self._default_decode
        )  # options.get('decode', self._default_decode)
        self.reconnect_after_ms: Callable[[int], int] = (
            options.reconnect_after_ms
            if options.reconnect_after_ms is not None
            else self._default_reconnect_after_ms
        )
        self.reconnect_timer: Timer = Timer(self._reconnect, self.reconnect_after_ms)
        self.access_token: Optional[str] = self.params.get("apikey", None)
        self.api_key = self.access_token
        self.channels: List["RealtimeChannel"] = []
        self.conn: Optional[websockets.client.WebSocketClientProtocol] = None
        self.send_buffer: List[Callable[[], None]] = []
        self.serializer: Serializer = Serializer()
        self.state_change_callbacks: Dict[str, List[Callable]] = {
            "open": [],
            "close": [],
            "error": [],
            "message": [],
        }
        self.pending_heartbeat_ref: Optional[str] = None
        self.ref: int = 0

    async def connect(self) -> None:
        if self.conn:
            return

        self.conn = await websockets.connect(self._endpoint_url())
        asyncio.create_task(self.setup_connection())

    async def disconnect(
        self, code: int = CloseCode.NORMAL_CLOSURE, reason: str = ""
    ) -> None:
        if self.conn:
            await self.conn.close(code, reason)
            self.conn = None
            self.reconnect_timer.reset()

    async def remove_channel(self, channel: "RealtimeChannel") -> str:
        status = await channel.unsubscribe()
        if not self.channels:
            await self.disconnect()
        return status

    async def remove_all_channels(self) -> List[str]:
        statuses = await asyncio.gather(
            *[channel.unsubscribe() for channel in self.channels]
        )
        await self.disconnect()
        return statuses

    def log(self, kind: str, msg: str, data: Any = None) -> None:
        self.logger(kind, msg, data)

    def connection_state(self) -> str:
        if self.conn:
            if self.conn.state == State.OPEN:
                return ConnectionState.OPEN
            elif self.conn.state == State.CLOSED:
                return ConnectionState.CLOSED
            elif self.conn.state == State.CONNECTING:
                return ConnectionState.CONNECTING
            elif self.conn.state == State.CLOSING:
                return ConnectionState.CLOSING
        return ConnectionState.CLOSED

    def is_connected(self) -> bool:
        return self.connection_state() == ConnectionState.OPEN

    def channel(
        self, topic: str, params: Optional[Dict[str, Any]] = None
    ) -> 'RealtimeChannel':
        from realtime.channel import RealtimeChannel
        params = params or {}
        chan = RealtimeChannel(self, f"realtime:{topic}", params)
        self.channels.append(chan)
        return chan

    def push(self, data: Dict[str, Any]) -> None:
        callback = lambda: self.conn.send(self.encode(data))
        self.log("push", f"{data}")
        if self.is_connected():
            callback()
        else:
            self.send_buffer.append(callback)

    def set_auth(self, token: Optional[str]) -> None:
        self.access_token = token
        for channel in self.channels:
            if token:
                channel.update_join_payload({"access_token": token})
            if channel.joined_once and channel.is_joined:
                channel._push(ChannelEvents.access_token, {"access_token": token})

    def _default_reconnect_after_ms(self, tries: int) -> int:
        return [1000, 2000, 5000, 10000][tries - 1] if tries <= 4 else 10000

    def _noop(self, *args: Any, **kwargs: Any) -> None:
        pass

    def _default_encode(
        self, payload: Dict[str, Any], callback: Callable[[str], None]
    ) -> None:
        callback(json.dumps(payload))

    def _default_decode(self, raw_message: str) -> Dict[str, Any]:
        return json.loads(raw_message)

    def _make_ref(self) -> str:
        self.ref += 1
        if self.ref == self.ref:
            self.ref = 0
        return str(self.ref)

    def _append_params(self, url: str, params: Dict[str, str]) -> str:
        if not params:
            return url
        query = urlencode(params)
        return f"{url}?{query}"

    def _http_endpoint_url(self, socket_url: str) -> str:
        url = re.sub(r"^ws", "http", socket_url, flags=re.IGNORECASE)
        url = re.sub(
            r"(\/socket\/websocket|\/socket|\/websocket)\/?$",
            "",
            url,
            flags=re.IGNORECASE,
        )
        url = re.sub(r"\/+$", "", url)
        return url

    async def setup_connection(self) -> None:
        async for msg in self.conn:
            await self._on_conn_message(msg)
        await self.conn.wait_closed()

    async def _on_conn_message(self, raw_message: str) -> None:
        msg = self.decode(raw_message)
        topic, event, payload, ref = (
            msg["topic"],
            msg["event"],
            msg["payload"],
            msg["ref"],
        )
        if ref == self.pending_heartbeat_ref or event == payload.get("type"):
            self.pending_heartbeat_ref = None
        self.log(
            "receive",
            f"{payload.get('status', '')} {topic} {event} ({ref or ''})",
            payload,
        )
        for channel in self.channels:
            if channel._is_member(topic):
                channel._trigger(event, payload, ref)
        for callback in self.state_change_callbacks["message"]:
            callback(msg)

    def _endpoint_url(self) -> str:
        return self._append_params(self.endpoint, {**self.params, "vsn": VSN})

    async def _reconnect(self) -> None:
        await self.disconnect()
        await self.connect()

    async def _send_heartbeat(self) -> None:
        if not self.is_connected():
            return
        if self.pending_heartbeat_ref:
            self.pending_heartbeat_ref = None
            self.log(
                "transport", "heartbeat timeout. Attempting to re-establish connection"
            )
            await self.conn.close(CloseCode.NORMAL_CLOSURE, "heartbeat timeout")
            return
        self.pending_heartbeat_ref = self._make_ref()
        self.push(
            {
                "topic": "phoenix",
                "event": "heartbeat",
                "payload": {},
                "ref": self.pending_heartbeat_ref,
            }
        )
        self.set_auth(self.access_token)
