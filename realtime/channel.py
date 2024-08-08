from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

import aiohttp

from realtime.connection import Socket
from realtime.message import ChannelEvents
from realtime.types import DEFAULT_TIMEOUT, ChannelState

if TYPE_CHECKING:
    pass


class Push:
    def __init__(
        self,
        channel: RealtimeChannel,
        event: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.channel = channel
        self.event = event
        self.payload = payload or {}
        self.timeout = timeout
        self.sent = False
        self.timeout_timer: Optional[asyncio.Task] = None
        self.ref = ""
        self.received_resp: Optional[Dict[str, Any]] = None
        self.rec_hooks: List[Dict[str, Union[str, Callable]]] = []
        self.ref_event: Optional[str] = None

    def resend(self, timeout: int):
        self.timeout = timeout
        self._cancel_ref_event()
        self.ref = ""
        self.ref_event = None
        self.received_resp = None
        self.sent = False
        self.send()

    def send(self):
        if self._has_received("timeout"):
            return
        self.start_timeout()
        self.sent = True
        self.channel.socket.push(
            {
                "topic": self.channel.topic,
                "event": self.event,
                "payload": self.payload,
                "ref": self.ref,
                "join_ref": self.channel._joinRef(),
            }
        )

    def update_payload(self, payload: Dict[str, Any]):
        self.payload.update(payload)

    def receive(self, status: str, callback: Callable):
        if self._has_received(status):
            callback(self.received_resp.get("response"))
        self.rec_hooks.append({"status": status, "callback": callback})
        return self

    def start_timeout(self):
        if self.timeout_timer:
            return
        self.ref = self.channel.socket._makeRef()
        self.ref_event = self.channel._replyEventName(self.ref)

        async def callback(payload: Any):
            self._cancel_ref_event()
            self._cancel_timeout()
            self.received_resp = payload
            self._match_receive(payload)

        self.channel._on(self.ref_event, {}, callback)

        self.timeout_timer = asyncio.create_task(self._timeout())

    async def _timeout(self):
        await asyncio.sleep(self.timeout / 1000)
        self.trigger("timeout", {})

    def trigger(self, status: str, response: Any):
        if self.ref_event:
            self.channel._trigger(
                self.ref_event, {"status": status, "response": response}
            )

    def destroy(self):
        self._cancel_ref_event()
        self._cancel_timeout()

    def _cancel_ref_event(self):
        if not self.ref_event:
            return
        self.channel._off(self.ref_event, {})

    def _cancel_timeout(self):
        if self.timeout_timer:
            self.timeout_timer.cancel()
            self.timeout_timer = None

    def _match_receive(self, payload: Dict[str, Any]):
        status = payload.get("status")
        response = payload.get("response")
        for hook in self.rec_hooks:
            if hook["status"] == status:
                hook["callback"](response)

    def _has_received(self, status: str) -> bool:
        return self.received_resp and self.received_resp.get("status") == status


class RealtimeChannel:
    def __init__(self, socket: Socket, topic: str, params: Dict[str, Any]):
        self.bindings: Dict[str, List[Dict[str, Any]]] = {}
        self.timeout: int = 10000
        self.state: ChannelState = ChannelState.CLOSED
        self.joined_once: bool = False
        self.push_buffer: List[Push] = []
        self.params = params or {"config": {}}
        self.params["config"] = {
            **{
                "broadcast": {"ack": False, "self": False},
                "presence": {"key": ""},
                "private": False,
            },
            **self.params["config"],
        }
        self.socket = socket
        self.topic = topic
        self.sub_topic = topic.replace("realtime:", "")
        self.join_push = Push(self, ChannelEvents.join, self.params, self.timeout)
        self.rejoin_timer: Optional[asyncio.Task] = None
        self.schedule_rejoin()
        self.broadcast_endpoint_url = f"{self.socket.endpoint}/api/broadcast"
        self.private = self.params["config"]["private"]

        self.join_push.receive("ok", self._on_join_ok)
        self.on_close(self._on_channel_close)
        self.on_error(self._on_channel_error)
        self.join_push.receive("timeout", self._on_join_timeout)
        self._on(ChannelEvents.reply, {}, self._on_channel_reply)

        from .presence import RealtimePresence

        self.presence = RealtimePresence(self)

    def schedule_rejoin(self) -> None:
        if self.rejoin_timer:
            self.rejoin_timer.cancel()
        self.rejoin_timer = asyncio.create_task(self._rejoin_after_delay())

    async def _rejoin_after_delay(self) -> None:
        await asyncio.sleep(self.socket.reconnect_after_ms / 1000)
        self._rejoin_until_connected()

    def _rejoin_until_connected(self) -> None:
        self._rejoin()
        if not self.socket.is_connected():
            self.schedule_rejoin()

    def _on_join_ok(self) -> None:
        self.state = ChannelState.JOINED
        self.rejoin_timer.reset()
        for push_event in self.push_buffer:
            push_event.send()
        self.push_buffer = []

    def _on_channel_close(self) -> None:
        if self.rejoin_timer:
            self.rejoin_timer.cancel()
        self.socket.log("channel", f"close {self.topic} {self._join_ref()}")
        self.state = ChannelState.CLOSED
        self.socket._remove(self)

    def _on_channel_error(self, reason: str) -> None:
        if self._is_leaving() or self._is_closed():
            return
        self.socket.log("channel", f"error {self.topic}", reason)
        self.state = ChannelState.ERRORED
        self.schedule_rejoin()

    def _on_join_timeout(self) -> None:
        if not self._is_joining():
            return
        self.socket.log("channel", f"timeout {self.topic}", self.join_push.timeout)
        self.state = ChannelState.ERRORED
        self.schedule_rejoin()

    def _on_channel_reply(self, payload: Dict[str, Any], ref: str) -> None:
        self._trigger(self._reply_event_name(ref), payload)

    def subscribe(
        self,
        callback: Optional[Callable[[str, Any], None]] = None,
        timeout: Optional[int] = None,
    ) -> RealtimeChannel:
        timeout = timeout or self.timeout
        if not self.socket.is_connected():
            self.socket.connect()

        if self.joined_once:
            raise Exception(
                "tried to subscribe multiple times. 'subscribe' can only be called a single time per channel instance"
            )
        else:
            config = self.params["config"]
            self.on_error(lambda e: callback and callback("CHANNEL_ERROR", e))
            self.on_close(lambda: callback and callback("CLOSED"))

            access_token_payload = {}
            config = {
                "broadcast": config["broadcast"],
                "presence": config["presence"],
                "postgres_changes": [
                    r["filter"] for r in self.bindings.get("postgres_changes", [])
                ],
                "private": config["private"],
            }

            if self.socket.access_token:
                access_token_payload["access_token"] = self.socket.access_token

            self.update_join_payload({**{"config": config}, **access_token_payload})
            self.joined_once = True
            self._rejoin(timeout)

            self.join_push.receive("ok", self._on_subscribe_ok(callback))
            self.join_push.receive("error", self._on_subscribe_error(callback))
            self.join_push.receive("timeout", self._on_subscribe_timeout(callback))

        return self

    def _on_subscribe_ok(
        self, callback: Optional[Callable[[str, Any], None]]
    ) -> Callable[[Dict[str, Any]], None]:
        def inner(response: Dict[str, Any]) -> None:
            server_postgres_filters = response.get("postgres_changes")
            if server_postgres_filters is None:
                callback and callback("SUBSCRIBED")
                return

            client_postgres_bindings = self.bindings.get("postgres_changes", [])
            new_postgres_bindings = []

            for i, client_postgres_binding in enumerate(client_postgres_bindings):
                server_postgres_filter = (
                    server_postgres_filters[i]
                    if i < len(server_postgres_filters)
                    else None
                )

                if (
                    server_postgres_filter
                    and server_postgres_filter["event"]
                    == client_postgres_binding["filter"]["event"]
                    and server_postgres_filter["schema"]
                    == client_postgres_binding["filter"]["schema"]
                    and server_postgres_filter["table"]
                    == client_postgres_binding["filter"]["table"]
                    and server_postgres_filter["filter"]
                    == client_postgres_binding["filter"]["filter"]
                ):
                    new_postgres_bindings.append(
                        {**client_postgres_binding, "id": server_postgres_filter["id"]}
                    )
                else:
                    self.unsubscribe()
                    callback and callback(
                        "CHANNEL_ERROR",
                        Exception(
                            "mismatch between server and client bindings for postgres changes"
                        ),
                    )
                    return

            self.bindings["postgres_changes"] = new_postgres_bindings
            callback and callback("SUBSCRIBED")

        return inner

    def _on_subscribe_error(
        self, callback: Optional[Callable[[str, Any], None]]
    ) -> Callable[[Dict[str, Any]], None]:
        def inner(error: Dict[str, Any]) -> None:
            callback and callback(
                "CHANNEL_ERROR", Exception(json.dumps(error.values()) or "error")
            )

        return inner

    def _on_subscribe_timeout(
        self, callback: Optional[Callable[[str, Any], None]]
    ) -> Callable[[], None]:
        def inner() -> None:
            callback and callback("TIMED_OUT")

        return inner

    def presence_state(self) -> Dict[str, Any]:
        return self.presence.state

    async def track(
        self, payload: Dict[str, Any], opts: Optional[Dict[str, Any]] = None
    ) -> Any:
        opts = opts or {}
        return await self.send(
            {
                "type": "presence",
                "event": "track",
                "payload": payload,
            },
            opts.get("timeout", self.timeout),
        )

    async def untrack(self, opts: Optional[Dict[str, Any]] = None) -> Any:
        opts = opts or {}
        return await self.send(
            {
                "type": "presence",
                "event": "untrack",
            },
            opts,
        )

    def on(
        self,
        type: str,
        filter: Dict[str, Any],
        callback: Callable[[Any, Optional[str]], None],
    ) -> RealtimeChannel:
        return self._on(type, filter, callback)

    async def send(
        self, args: Dict[str, Any], opts: Optional[Dict[str, Any]] = None
    ) -> str:
        opts = opts or {}
        if not self._can_push() and args["type"] == "broadcast":
            options = {
                "headers": {
                    "Authorization": (
                        f"Bearer {self.socket.access_token}"
                        if self.socket.access_token
                        else ""
                    ),
                    "apikey": self.socket.api_key if self.socket.api_key else "",
                    "Content-Type": "application/json",
                },
                "json": {
                    "messages": [
                        {
                            "topic": self.sub_topic,
                            "event": args["event"],
                            "payload": args["payload"],
                            "private": self.private,
                        }
                    ]
                },
            }
            try:
                response = await self._fetch_with_timeout(
                    self.broadcast_endpoint_url,
                    options,
                    opts.get("timeout", self.timeout),
                )
                return "ok" if response and response.status < 300 else "error"
            except aiohttp.ClientError:
                return "error"
        else:
            return await self._push(
                args["type"], args, opts.get("timeout", self.timeout)
            )

    def update_join_payload(self, payload: Dict[str, Any]) -> None:
        self.join_push.update_payload(payload)

    async def unsubscribe(self, timeout: Optional[int] = None) -> str:
        timeout = timeout or self.timeout
        self.state = ChannelState.LEAVING
        on_close = lambda: self.socket.log(
            "channel", f"leave {self.topic}"
        ) or self._trigger(ChannelEvents.close, "leave", self._join_ref())
        self.rejoin_timer.reset()
        self.join_push.destroy()

        promise = asyncio.Event()

        leave_push = Push(self, ChannelEvents.leave, {}, timeout)
        leave_push.receive("ok", lambda: on_close() or promise.set())
        leave_push.receive("timeout", lambda: on_close() or promise.set())
        leave_push.receive("error", lambda: promise.set())
        leave_push.send()

        if not self._can_push():
            leave_push.trigger("ok", {})

        return "ok" if await asyncio.wait_for(promise.wait(), timeout) else "timed out"

    async def _fetch_with_timeout(
        self, url: str, options: Dict[str, Any], timeout: float
    ) -> Optional[aiohttp.ClientResponse]:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, **options, timeout=timeout) as response:
                    await response.text()  # Ensure the response body is read
                    return response
            except asyncio.TimeoutError:
                return None

    def _push(
        self, event: str, payload: Dict[str, Any], timeout: Optional[int] = None
    ) -> Push:
        if not self.joined_once:
            raise Exception(
                f"tried to push '{event}' to '{self.topic}' before joining. Use channel.subscribe() before pushing events"
            )
        push_event = Push(self, event, payload, timeout)
        if self._can_push():
            push_event.send()
        else:
            push_event.start_timeout()
            self.push_buffer.append(push_event)
        return push_event

    def _on(
        self,
        type: str,
        filter: Dict[str, Any],
        callback: Callable[[Any, Optional[str]], None],
    ) -> RealtimeChannel:
        self.bindings[type] = self.bindings.get(type, [])
        binding = {
            "type": type,
            "filter": filter,
            "callback": callback,
        }
        self.bindings[type].append(binding)
        return self

    def _off(self, type: str, filter: Dict[str, Any]) -> RealtimeChannel:
        if type in self.bindings:
            self.bindings[type] = [
                b for b in self.bindings[type] if b["filter"] != filter
            ]
        return self

    def _can_push(self) -> bool:
        return self.socket.is_connected() and self._is_joined()

    def _is_member(self, type: str, filter: Dict[str, Any]) -> bool:
        return any(
            b["type"] == type and b["filter"] == filter
            for b in self.bindings.get(type, [])
        )

    def _join_ref(self) -> str:
        return self.join_push.ref

    def _rejoin(self, timeout: Optional[int] = None) -> None:
        timeout = timeout or self.timeout
        if self.state in {ChannelState.LEAVING, ChannelState.CLOSED}:
            return
        self.socket._leave_open_topic(self.topic)
        self.state = ChannelState.JOINING
        self.join_push.resend(timeout)

    def _trigger(
        self,
        type: str,
        filter: Dict[str, Any],
        payload: Any = None,
        ref: Optional[str] = None,
    ) -> None:
        for binding in self.bindings.get(type, []):
            if binding["filter"] == filter:
                binding["callback"](payload, ref)

    def _reply_event_name(self, ref: str) -> str:
        return f"resp_{ref}"

    @property
    def is_closed(self) -> bool:
        return self.state == ChannelState.CLOSED

    @property
    def is_joined(self) -> bool:
        return self.state == ChannelState.JOINED

    @property
    def is_joining(self) -> bool:
        return self.state == ChannelState.JOINING

    @property
    def is_leaving(self) -> bool:
        return self.state == ChannelState.LEAVING

    def on_close(self, callback: Callable[[], None]) -> None:
        self._on(ChannelState.CLOSED, {}, callback)

    def on_error(self, callback: Callable[[Any], None]) -> None:
        self._on(ChannelState.ERRORED, {}, lambda e: callback(e))
