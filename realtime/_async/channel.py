from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from realtime.types import (
    Binding,
    Callback,
    ChannelEvents,
    ChannelStates,
    RealtimeChannelOptions,
    RealtimePostgresChangesListenEvent,
    RealtimePresenceState,
    RealtimeSubscribeStates,
)

from ..transformers import http_endpoint_url
from .presence import (
    AsyncRealtimePresence,
    PresenceOnJoinCallback,
    PresenceOnLeaveCallback,
)
from .push import AsyncPush
from .timer import AsyncTimer

if TYPE_CHECKING:
    from .client import AsyncRealtimeClient

logger = logging.getLogger(__name__)


class AsyncRealtimeChannel:
    """
    Channel is an abstraction for a topic subscription on an existing socket connection.
    Each Channel has its own topic and a list of event-callbacks that respond to messages.
    Should only be instantiated through `AsyncRealtimeClient.channel(topic)`.
    """

    def __init__(
        self,
        socket: AsyncRealtimeClient,
        topic: str,
        params: Optional[RealtimeChannelOptions] = None,
    ) -> None:
        """
        Initialize the Channel object.

        :param socket: RealtimeClient object
        :param topic: Topic that it subscribes to on the realtime server
        :param params: Optional parameters for connection.
        """
        self.socket = socket
        self.params = params or {}
        if self.params.get("config") is None:
            self.params["config"] = {
                "broadcast": {"ack": False, "self": False},
                "presence": {"key": ""},
                "private": False,
            }

        self.topic = topic
        self._joined_once = False
        self.bindings: Dict[str, List[Binding]] = {}
        self.presence = AsyncRealtimePresence(self)
        self.state = ChannelStates.CLOSED
        self._push_buffer: List[AsyncPush] = []
        self.timeout = self.socket.timeout

        self.join_push = AsyncPush(self, ChannelEvents.join, self.params)
        self.rejoin_timer = AsyncTimer(
            self._rejoin_until_connected, lambda tries: 2**tries
        )

        self.broadcast_endpoint_url = self._broadcast_endpoint_url()

        def on_join_push_ok(payload: Dict[str, Any], *args):
            self.state = ChannelStates.JOINED
            self.rejoin_timer.reset()
            for push in self._push_buffer:
                asyncio.create_task(push.send())
            self._push_buffer = []

        def on_join_push_timeout(*args):
            if not self.is_joining:
                return

            logger.error(f"join push timeout for channel {self.topic}")
            self.state = ChannelStates.ERRORED
            self.rejoin_timer.schedule_timeout()

        self.join_push.receive("ok", on_join_push_ok).receive(
            "timeout", on_join_push_timeout
        )

        def on_close(*args):
            logger.info(f"channel {self.topic} closed")
            self.rejoin_timer.reset()
            self.state = ChannelStates.CLOSED
            self.socket._remove_channel(self)

        def on_error(payload, *args):
            if self.is_leaving or self.is_closed:
                return

            logger.info(f"channel {self.topic} error: {payload}")
            self.state = ChannelStates.ERRORED
            self.rejoin_timer.schedule_timeout()

        self._on("close", on_close)
        self._on("error", on_error)

        def on_reply(payload, ref):
            self._trigger(self._reply_event_name(ref), payload)

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
            Callable[[RealtimeSubscribeStates, Optional[Exception]], None]
        ] = None,
    ) -> AsyncRealtimeChannel:
        """
        Subscribe to the channel. Can only be called once per channel instance.

        :param callback: Optional callback function that receives subscription state updates
                        and any errors that occur during subscription
        :return: The Channel instance for method chaining
        :raises: Exception if called multiple times on the same channel instance
        """
        if not self.socket.is_connected:
            await self.socket.connect()

        if self._joined_once:
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
            self._joined_once = True

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
                        asyncio.create_task(self.unsubscribe())
                        callback and callback(
                            RealtimeSubscribeStates.CHANNEL_ERROR,
                            Exception(
                                "mismatch between server and client bindings for postgres changes"
                            ),
                        )
                        return

                self.bindings["postgres_changes"] = new_postgres_bindings
                callback and callback(RealtimeSubscribeStates.SUBSCRIBED, None)

            def on_join_push_error(payload: Dict[str, Any]):
                callback and callback(
                    RealtimeSubscribeStates.CHANNEL_ERROR,
                    Exception(json.dumps(payload)),
                )

            def on_join_push_timeout(*args):
                callback and callback(RealtimeSubscribeStates.TIMED_OUT, None)

            self.join_push.receive("ok", on_join_push_ok).receive(
                "error", on_join_push_error
            ).receive("timeout", on_join_push_timeout)

            await self._rejoin()

        return self

    async def unsubscribe(self):
        """
        Unsubscribe from the channel and leave the topic.
        Sets channel state to LEAVING and cleans up timers and pushes.
        """
        self.state = ChannelStates.LEAVING

        self.rejoin_timer.reset()
        self.join_push.destroy()

        def _close(*args):
            logger.info(f"channel {self.topic} leave")
            self._trigger(ChannelEvents.close, "leave")

        leave_push = AsyncPush(self, ChannelEvents.leave, {})
        leave_push.receive("ok", _close).receive("timeout", _close)

        await leave_push.send()

        if not self._can_push():
            leave_push.trigger("ok", {})

    async def push(
        self, event: str, payload: Dict[str, Any], timeout: Optional[int] = None
    ) -> AsyncPush:
        """
        Push a message to the channel.

        :param event: The event name to push
        :param payload: The payload to send
        :param timeout: Optional timeout in milliseconds
        :return: AsyncPush instance representing the push operation
        :raises: Exception if called before subscribing to the channel
        """
        if not self._joined_once:
            raise Exception(
                f"tried to push '{event}' to '{self.topic}' before joining. Use channel.subscribe() before pushing events"
            )

        timeout = timeout or self.timeout

        push = AsyncPush(self, event, payload, timeout)
        if self._can_push():
            await push.send()
        else:
            push.start_timeout()
            self._push_buffer.append(push)

        return push

    async def join(self) -> AsyncRealtimeChannel:
        """
        Coroutine that attempts to join Phoenix Realtime server via a certain topic.

        :return: Channel
        """
        try:
            await self.socket.send(
                {
                    "topic": self.topic,
                    "event": "phx_join",
                    "payload": {"config": self.params},
                    "ref": None,
                }
            )
        except Exception as e:
            print(e)
            return self

    # Event handling methods
    def _on(
        self, type: str, callback: Callback, filter: Optional[Dict[str, Any]] = None
    ) -> AsyncRealtimeChannel:
        """
        Set up a listener for a specific event.

        :param type: The type of the event to listen for.
        :param filter: Additional parameters for the event.
        :param callback: The callback function to execute when the event is received.
        :return: The Channel instance for method chaining.
        """

        type_lowercase = type.lower()
        binding = Binding(type=type_lowercase, filter=filter or {}, callback=callback)
        self.bindings.setdefault(type_lowercase, []).append(binding)

        return self

    def _off(self, type: str, filter: Dict[str, Any]) -> AsyncRealtimeChannel:
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

    def on_broadcast(
        self, event: str, callback: Callable[[Dict[str, Any]], None]
    ) -> AsyncRealtimeChannel:
        """
        Set up a listener for a specific broadcast event.

        :param event: The name of the broadcast event to listen for
        :param callback: Function called with the payload when a matching broadcast is received
        :return: The Channel instance for method chaining
        """
        return self._on(
            "broadcast",
            filter={"event": event},
            callback=lambda payload, _: callback(payload),
        )

    def on_postgres_changes(
        self,
        event: RealtimePostgresChangesListenEvent,
        callback: Callable[[Dict[str, Any]], None],
        table: str = "*",
        schema: str = "public",
        filter: Optional[str] = None,
    ) -> AsyncRealtimeChannel:
        """
        Set up a listener for Postgres database changes.

        :param event: The type of database event to listen for (INSERT, UPDATE, DELETE, or *)
        :param callback: Function called with the payload when a matching change is detected
        :param table: The table name to monitor. Defaults to "*" for all tables
        :param schema: The database schema to monitor. Defaults to "public"
        :param filter: Optional filter string to apply
        :return: The Channel instance for method chaining
        """

        binding_filter = {"event": event, "schema": schema, "table": table}
        if filter:
            binding_filter["filter"] = filter

        return self._on(
            "postgres_changes",
            filter=binding_filter,
            callback=lambda payload, _: callback(payload),
        )

    def on_system(
        self, callback: Callable[[Dict[str, Any], None]]
    ) -> AsyncRealtimeChannel:
        """
        Set up a listener for system events.

        :param callback: The callback function to execute when a system event is received.
        :return: The Channel instance for method chaining.
        """
        return self._on("system", callback=lambda payload, _: callback(payload))

    # Presence methods
    async def track(self, user_status: Dict[str, Any]) -> None:
        """
        Track presence status for the current user.

        :param user_status: Dictionary containing the user's presence information
        """
        await self.send_presence("track", user_status)

    async def untrack(self) -> None:
        """
        Stop tracking presence for the current user.
        """
        await self.send_presence("untrack", {})

    def presence_state(self) -> RealtimePresenceState:
        """
        Get the current state of presence on this channel.

        :return: Dictionary mapping presence keys to lists of presence payloads
        """
        return self.presence.state

    def on_presence_sync(self, callback: Callable[[], None]) -> AsyncRealtimeChannel:
        """
        Register a callback for presence sync events.

        :param callback: The callback function to execute when a presence sync event occurs.
        :return: The Channel instance for method chaining.
        """
        self.presence.on_sync(callback)
        return self

    def on_presence_join(
        self, callback: PresenceOnJoinCallback
    ) -> AsyncRealtimeChannel:
        """
        Register a callback for presence join events.

        :param callback: The callback function to execute when a presence join event occurs.
        :return: The Channel instance for method chaining.
        """
        self.presence.on_join(callback)
        return self

    def on_presence_leave(
        self, callback: PresenceOnLeaveCallback
    ) -> AsyncRealtimeChannel:
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
        Send a broadcast message through this channel.

        :param event: The name of the broadcast event
        :param data: The payload to broadcast
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
        return self.socket.is_connected and self._joined_once

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
                binding.callback(payload, ref)
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
                        binding.callback(payload, ref)
                    elif bind_event in [payload_event, "*"]:
                        binding.callback(payload, ref)
                elif binding.type == type_lowercase:
                    binding.callback(payload, ref)

    def _reply_event_name(self, ref: str):
        return f"chan_reply_{ref}"

    async def _rejoin_until_connected(self):
        self.rejoin_timer.schedule_timeout()
        if self.socket.is_connected:
            await self._rejoin()
