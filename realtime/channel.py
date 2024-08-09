from __future__ import annotations

import asyncio
import json
import logging
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from realtime.timer import Timer
from realtime.types import DEFAULT_TIMEOUT, Callback, ChannelEvents, ChannelStates

from .presence import PresenceOnJoinCallback, PresenceOnLeaveCallback, RealtimePresence
from .transformers import http_endpoint_url

if TYPE_CHECKING:
    from realtime.connection import Socket


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


class Hook:
    def __init__(self, status: str, callback: Callback):
        self.status = status
        self.callback = callback


class Push:
    def __init__(
        self,
        channel: Channel,
        event: str,
        payload: Dict[str, Any] = {},
        timeout=DEFAULT_TIMEOUT,
    ):
        self.channel = channel
        self.event = event
        self.payload = payload
        self.timeout = timeout
        self.rec_hooks: List[Hook] = []
        self.ref = None
        self.ref_event = None
        self.received_resp: Optional[Dict[str, Any]] = None
        self.sent = False
        self.timeout_task = None

    async def resend(self):
        self._cancel_ref_event()
        self.ref = ""
        self.ref_event = None
        self.received_resp = None
        self.sent = False
        await self.send()

    async def send(self):
        if self._has_received("timeout"):
            return

        self.start_timeout()
        self.sent = True

        try:
            await self.channel.socket.send(
                {
                    "topic": self.channel.topic,
                    "event": self.event,
                    "payload": self.payload,
                    "ref": self.ref,
                    "join_ref": self.channel.join_push.ref,
                }
            )
        except Exception as e:
            logging.error(f"send push failed: {e}")

    def update_payload(self, payload: Dict[str, Any]):
        self.payload = {**self.payload, **payload}

    def receive(self, status: str, callback: Callback) -> Push:
        if self._has_received(status):
            callback(self.received_resp.get("response", {}))

        self.rec_hooks.append(Hook(status, callback))
        return self

    def start_timeout(self):
        if self.timeout_task:
            return

        self.ref = self.channel.socket._make_ref()
        self.ref_event = self.channel._reply_event_name(self.ref)

        def on_reply(**kwargs):
            self._cancel_ref_event()
            self._cancel_timeout()
            self.received_resp = kwargs.get("payload")
            self._match_receive(**self.received_resp)

        self.channel._on(self.ref_event, on_reply)

        async def timeout(self):
            await asyncio.sleep(self.timeout)
            self.trigger("timeout", {})

        self.timeout_task = asyncio.create_task(timeout(self))

    def trigger(self, status: str, response: Any):
        if self.ref_event:
            payload = {
                "status": status,
                "response": response,
            }
            self.channel._trigger(self.ref_event, payload)

    def destroy(self):
        self._cancel_ref_event()
        self._cancel_timeout()

    def _cancel_ref_event(self):
        if not self.ref_event:
            return

        self.channel._off(self.ref_event, {})

    def _cancel_timeout(self):
        if not self.timeout_task:
            return

        self.timeout_task.cancel()
        self.timeout_task = None

    def _match_receive(self, status: str, response: Any):
        for hook in self.rec_hooks:
            if hook.status == status:
                # FIXME: callback can be a coroutine, how to handle that?
                hook.callback(response)

    def _has_received(self, status: str):
        return self.received_resp and self.received_resp.get("status") == status


class RealtimeSubscribeStates(str, Enum):
    SUBSCRIBED = "SUBSCRIBED"
    TIMED_OUT = "TIMED_OUT"
    CLOSED = "CLOSED"
    CHANNEL_ERROR = "CHANNEL_ERROR"


class Channel:
    """
    `Channel` is an abstraction for a topic listener for an existing socket connection.
    Each Channel has its own topic and a list of event-callbacks that responds to messages.
    Should only be instantiated through `connection.Socket().channel(topic)`.
    """

    def __init__(
        self,
        socket: Socket,
        topic: str,
        params: Dict[str, Any] = {"config": {}},
    ) -> None:
        """
        Initialize the Channel object.

        :param socket: Socket object
        :param topic: Topic that it subscribes to on the realtime server
        :param params: Optional parameters for connection.
        """
        self.socket = socket
        self.params = params
        self.topic = topic
        self.joined = False
        self.bindings: Dict[str, List[Binding]] = {}
        self.presence = RealtimePresence(self)
        self.filter = None
        self.current_event = None
        self.state = ChannelStates.CLOSED
        self.push_buffer: List[Push] = []
        self.timeout = self.socket.timeout
        self.params["config"] = {
            "broadcast": {"ack": False, "self": False},
            "presence": {"key": ""},
            "private": False,
            **params.get("config", {}),
        }

        self.join_push = Push(self, ChannelEvents.join, self.params)
        self.rejoin_timer = Timer(self._rejoin_until_connected, lambda tries: 2**tries)

        self.broadcast_endpoint_url = self._broadcast_endpoint_url()

        def on_join_push_ok(payload: Dict[str, Any], **kwargs):
            self.state = ChannelStates.JOINED
            self.rejoin_timer.reset()
            for push in self.push_buffer:
                asyncio.create_task(push.send())
            self.push_buffer = []

        def on_join_push_timeout(**kwargs):
            if not self.is_joining:
                return

            logging.error(f"join push timeout for channel {self.topic}")
            self.state = ChannelStates.ERRORED
            self.rejoin_timer.schedule_timeout()

        self.join_push.receive("ok", on_join_push_ok).receive(
            "timeout", on_join_push_timeout
        )

        def on_close(**kwargs):
            logging.info(f"channel {self.topic} closed")
            self.rejoin_timer.reset()
            self.state = ChannelStates.CLOSED
            self.socket._remove(self)

        def on_error(**kwargs):
            if self.is_leaving or self.is_closed:
                return

            logging.info(f"channel {self.topic} error: {kwargs.get('payload')}")
            self.state = ChannelStates.ERRORED
            self.rejoin_timer.schedule_timeout()

        self._on("close", on_close)
        self._on("error", on_error)

        def on_reply(**kwargs):
            self._trigger(
                self._reply_event_name(kwargs.get("ref")), kwargs.get("payload")
            )

        self._on(ChannelEvents.reply, on_reply)

    # Properties
    @property
    def is_closed(self):
        return self.state == ChannelStates.CLOSED

    @property
    def is_joining(self):
        return self.state == ChannelStates.JOINING

    @property
    def is_leaving(self):
        return self.state == ChannelStates.LEAVING

    @property
    def is_errored(self):
        return self.state == ChannelStates.ERRORED

    @property
    def is_joined(self):
        return self.state == ChannelStates.JOINED

    @property
    def join_ref(self):
        return self.join_push.ref

    # Core channel methods
    async def subscribe(
        self,
        callback: Optional[
            Callable[[RealtimeSubscribeStates], Optional[Exception]]
        ] = None,
    ) -> Channel:
        """
        Subscribe to the channel.

        :return: The Channel instance for method chaining.
        """
        if not self.socket.is_connected:
            self.socket.connect()
        if self.joined:
            raise Exception(
                "Tried to subscribe multiple times. 'subscribe' can only be called a single time per channel instance"
            )
        else:
            config = self.params.get("config", {})
            broadcast = config.get("broadcast", {})
            presence = config.get("presence", {})
            private = config.get("private", False)

            access_token_payload = {}
            config = {
                "broadcast": broadcast,
                "presence": presence,
                "private": private,
                "postgres_changes": list(
                    map(lambda x: x.filter, self.bindings.get("postgres_changes", []))
                ),
            }

            if self.socket.access_token:
                access_token_payload["access_token"] = self.socket.access_token

            self.join_push.update_payload(
                {**{"config": config}, **access_token_payload}
            )
            self.joined = True

            def on_join_push_ok(payload: Dict[str, Any]):
                server_postgres_changes: List[Dict[str, Any]] = payload.get(
                    "postgres_changes", []
                )

                if len(server_postgres_changes) == 0:
                    callback and callback(RealtimeSubscribeStates.SUBSCRIBED, None)
                    return

                client_postgres_changes = self.bindings.get("postgres_changes", [])
                new_postgres_bindings = []

                bindings_len = len(client_postgres_changes)

                for i in range(bindings_len):
                    client_binding = client_postgres_changes[i]
                    event = client_binding.filter.get("event")
                    schema = client_binding.filter.get("schema")
                    table = client_binding.filter.get("table")
                    filter = client_binding.filter.get("filter")

                    server_binding = (
                        server_postgres_changes[i]
                        if i < len(server_postgres_changes)
                        else None
                    )

                    if (
                        server_binding
                        and server_binding.get("event") == event
                        and server_binding.get("schema") == schema
                        and server_binding.get("table") == table
                        and server_binding.get("filter") == filter
                    ):
                        client_binding.id = server_binding.get("id")
                        new_postgres_bindings.append(client_binding)
                    else:
                        self.unsubscribe()
                        return

                self.bindings["postgres_changes"] = new_postgres_bindings
                callback and callback(RealtimeSubscribeStates.SUBSCRIBED, None)

            def on_join_push_error(payload: Dict[str, Any]):
                callback and callback(
                    RealtimeSubscribeStates.CHANNEL_ERROR,
                    Exception(json.dumps(payload)),
                )

            def on_join_push_timeout():
                callback and callback(RealtimeSubscribeStates.TIMED_OUT, None)

            self.join_push.receive("ok", on_join_push_ok).receive(
                "error", on_join_push_error
            ).receive("timeout", on_join_push_timeout)

            await self._rejoin()

        return self

    async def unsubscribe(self):
        self.state = ChannelStates.LEAVING

        self.rejoin_timer.reset()
        self.join_push.destroy()

        def _on_close(**kwargs):
            logging.info(f"channel {self.topic} leave")
            self._trigger(ChannelEvents.close, "leave")

        leave_push = Push(self, ChannelEvents.leave, {})
        leave_push.receive("ok", _on_close).receive("timeout", _on_close)

        await leave_push.send()

        if not self._can_push():
            leave_push.trigger("ok", {})

    async def push(
        self, event: str, payload: Dict[str, Any], timeout: Optional[int] = None
    ) -> Push:
        if not self.joined:
            raise Exception(
                f"tried to push '{event}' to '{self.topic}' before joining. Use channel.subscribe() before pushing events"
            )

        timeout = timeout or self.timeout

        push = Push(self, event, payload, timeout)
        if self._can_push():
            await push.send()
        else:
            push.start_timeout()
            self.push_buffer.append(push)

        return push

    async def join(self) -> Channel:
        """
        Coroutine that attempts to join Phoenix Realtime server via a certain topic.

        :return: Channel
        """
        try:
            await self.socket._send(
                {
                    "topic": self.topic,
                    "event": "phx_join",
                    "payload": {"config": self.channel_params},
                    "ref": None,
                }
            )
        except Exception as e:
            print(e)
            return self

    def off(self, event: str) -> None:
        """
        Stop responding to a certain event.

        :param event: The event to stop responding to.
        :return: None
        """
        self.listeners = [
            callback for callback in self.listeners if callback.event != event
        ]

    # Event handling methods
    def _on(
        self, type: str, callback: Callback, filter: Dict[str, Any] = {}
    ) -> Channel:
        """
        Set up a listener for a specific event.

        :param type: The type of the event to listen for.
        :param filter: Additional parameters for the event.
        :param callback: The callback function to execute when the event is received.
        :return: The Channel instance for method chaining.
        """

        type_lowercase = type.lower()
        binding = Binding(type=type_lowercase, filter=filter, callback=callback)
        self.bindings.setdefault(type_lowercase, []).append(binding)

        return self

    def _off(self, type: str, filter: Dict[str, Any]) -> Channel:
        """
        Remove a listener for a specific event type and filter.

        :param type: The type of the event to remove the listener for.
        :param filter: The filter associated with the listener to remove.
        :return: The Channel instance for method chaining.

        This method removes all bindings for the specified event type that match
        the given filter. If no matching bindings are found, the method does nothing.
        """
        type_lowercase = type.lower()

        if type_lowercase in self.bindings:
            self.bindings[type_lowercase] = [
                binding
                for binding in self.bindings[type_lowercase]
                if binding.filter != filter
            ]
        return self

    def on_broadcast(self, event: str, callback: Callback) -> Channel:
        """
        Set up a listener for a specific broadcast event.

        :param event: The name of the broadcast event to listen for.
        :param callback: The callback function to execute when the event is received.
        :return: The Channel instance for method chaining.
        """
        return self._on("broadcast", filter={"event": event}, callback=callback)

    def on_postgres_changes(
        self, event: str, table: str, callback: Callback, schema: str = "public"
    ) -> Channel:
        """
        Set up a listener for a specific Postgres changes event.

        :param event: The name of the Postgres changes event to listen for.
        :param table: The table name for which changes should be monitored.
        :param callback: The callback function to execute when the event is received.
        :param schema: The database schema where the table exists. Default is 'public'.
        :return: The Channel instance for method chaining.
        """
        return self._on(
            "postgres_changes",
            filter={"event": event, "schema": schema, "table": table},
            callback=callback,
        )

    # Filter methods
    def eq(self, column: str, value: Any) -> Channel:
        """
        Set up a filter for equality.

        :param column: The column to filter on.
        :param value: The value to compare against.
        :return: The Channel instance for method chaining.
        """
        self.filter = f"{column}=eq.{value}"
        return self

    def neq(self, column: str, value: Any) -> Channel:
        """
        Set up a filter for inequality.

        :param column: The column to filter on.
        :param value: The value to compare against.
        :return: The Channel instance for method chaining.
        """
        self.filter = f"{column}=neq.{value}"
        return self

    def lt(self, column: str, value: Any) -> Channel:
        """
        Set up a filter for less than comparison.

        :param column: The column to filter on.
        :param value: The value to compare against.
        :return: The Channel instance for method chaining.
        """
        self.filter = f"{column}=lt.{value}"
        return self

    def lte(self, column: str, value: Any) -> Channel:
        """
        Set up a filter for less than or equal to comparison.

        :param column: The column to filter on.
        :param value: The value to compare against.
        :return: The Channel instance for method chaining.
        """
        self.filter = f"{column}=lte.{value}"
        return self

    def gt(self, column: str, value: Any) -> Channel:
        """
        Set up a filter for greater than comparison.

        :param column: The column to filter on.
        :param value: The value to compare against.
        :return: The Channel instance for method chaining.
        """
        self.filter = f"{column}=gt.{value}"
        return self

    def gte(self, column: str, value: Any) -> Channel:
        """
        Set up a filter for greater than or equal to comparison.

        :param column: The column to filter on.
        :param value: The value to compare against.
        :return: The Channel instance for method chaining.
        """
        self.filter = f"{column}=gte.{value}"
        return self

    def in_(self, column: str, values: List[Any]) -> Channel:
        """
        Set up a filter for containment within a list.

        :param column: The column to filter on.
        :param values: The list of values to check for containment.
        :return: The Channel instance for method chaining.
        """
        self.filter = f"{column}=in.({','.join(values)})"
        return self

    # Presence methods
    async def track(self, user_status: Dict[str, Any]) -> None:
        """
        Track a user's presence.

        :param user_status: User's presence status.
        :return: None
        """
        await self.send_presence("track", user_status)

    async def untrack(self) -> None:
        """
        Untrack a user's presence.

        :return: None
        """
        await self.send_presence("untrack", {})

    def on_presence_sync(self, callback: Callable[[], None]) -> Channel:
        """
        Register a callback for presence sync events.

        :param callback: The callback function to execute when a presence sync event occurs.
        :return: The Channel instance for method chaining.
        """
        self.presence.on_sync(callback)
        return self

    def on_presence_join(self, callback: PresenceOnJoinCallback) -> Channel:
        """
        Register a callback for presence join events.

        :param callback: The callback function to execute when a presence join event occurs.
        :return: The Channel instance for method chaining.
        """
        self.presence.on_join(callback)
        return self

    def on_presence_leave(self, callback: PresenceOnLeaveCallback) -> Channel:
        """
        Register a callback for presence leave events.

        :param callback: The callback function to execute when a presence leave event occurs.
        :return: The Channel instance for method chaining.
        """
        self.presence.on_leave(callback)
        return self

    # Broadcast methods
    async def send_broadcast(self, event: str, data: Any) -> None:
        """
        Sends a broadcast message to the current channel.

        :param event: The name of the broadcast event.
        :param data: The data to be sent with the message.
        :return: An asyncio.Future object representing the send operation.
        """
        await self.push(
            ChannelEvents.broadcast,
            {"type": "broadcast", "event": event, "payload": data},
        )

    # Internal methods
    def _broadcast_endpoint_url(self):
        return f"{http_endpoint_url(self.socket.http_endpoint)}/api/broadcast"

    async def _rejoin(self) -> None:
        if self.is_leaving:
            return
        await self.socket._leave_open_topic(self.topic)
        self.state = ChannelStates.JOINING
        await self.join_push.resend()

    def _can_push(self):
        return self.socket.is_connected and self.joined

    async def send_presence(self, event: str, data: Any) -> None:
        await self.push(ChannelEvents.presence, {"event": event, "payload": data})

    def _trigger(self, type: str, payload: Optional[Any], ref: Optional[str] = None):
        type_lowercase = type.lower()
        events = [
            ChannelEvents.close,
            ChannelEvents.error,
            ChannelEvents.leave,
            ChannelEvents.join,
        ]

        if ref is not None and type_lowercase in events and ref != self.join_push.ref:
            return

        if type_lowercase in ["insert", "update", "delete"]:
            postgres_changes = filter(
                lambda binding: binding.filter.get("event", "").lower()
                in [type_lowercase, "*"],
                self.bindings.get("postgres_changes", []),
            )
            for binding in postgres_changes:
                binding.callback(payload=payload, ref=ref)
        else:
            bindings = self.bindings.get(type_lowercase, [])
            for binding in bindings:
                if type_lowercase in ["broadcast", "postgres_changes", "presence"]:
                    bind_id = binding.id
                    bind_event = (
                        binding.filter.get("event", "").lower()
                        if binding.filter.get("event")
                        else None
                    )
                    payload_event = (
                        payload.get("event", "").lower()
                        if payload.get("event")
                        else None
                    )
                    data_type = (
                        payload.get("data", {}).get("type", "").lower()
                        if payload.get("data", {}).get("type")
                        else None
                    )
                    if (
                        bind_id
                        and bind_id in payload.get("ids", [])
                        and (bind_event == data_type or bind_event == "*")
                    ):
                        binding.callback(payload=payload, ref=ref)
                    elif bind_event in [payload_event, "*"]:
                        binding.callback(payload=payload, ref=ref)
                elif binding.type == type_lowercase:
                    binding.callback(payload=payload, ref=ref)

    def _reply_event_name(self, ref: str):
        return f"chan_reply_{ref}"

    async def _rejoin_until_connected(self):
        await self.rejoin_timer.schedule_timeout()
        if self.socket.is_connected:
            await self._rejoin()
