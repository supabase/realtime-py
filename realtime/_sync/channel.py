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
    PresenceOnJoinCallback,
    PresenceOnLeaveCallback,
    SyncRealtimePresence,
)
from .push import SyncPush
from .timer import SyncTimer

if TYPE_CHECKING:
    from .client import SyncRealtimeClient


class SyncRealtimeChannel:
    """
    `Channel` is an abstraction for a topic listener for an existing socket connection.
    Each Channel has its own topic and a list of event-callbacks that responds to messages.
    Should only be instantiated through `connection.RealtimeClient().channel(topic)`.
    """

    def __init__(
        self,
        socket: SyncRealtimeClient,
        topic: str,
        params: RealtimeChannelOptions = {"config": {}},
    ) -> None:
        """
        Initialize the Channel object.

        :param socket: RealtimeClient object
        :param topic: Topic that it subscribes to on the realtime server
        :param params: Optional parameters for connection.
        """
        self.socket = socket
        self.params = params
        self.topic = topic
        self._joined_once = False
        self.bindings: Dict[str, List[Binding]] = {}
        self.presence = SyncRealtimePresence(self)
        self.state = ChannelStates.CLOSED
        self._push_buffer: List[SyncPush] = []
        self.timeout = self.socket.timeout
        self.params["config"] = {
            "broadcast": {"ack": False, "self": False},
            "presence": {"key": ""},
            "private": False,
            **params.get("config", {}),
        }

        self.join_push = SyncPush(self, ChannelEvents.join, self.params)
        self.rejoin_timer = SyncTimer(
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

            logging.error(f"join push timeout for channel {self.topic}")
            self.state = ChannelStates.ERRORED
            self.rejoin_timer.schedule_timeout()

        self.join_push.receive("ok", on_join_push_ok).receive(
            "timeout", on_join_push_timeout
        )

        def on_close(*args):
            logging.info(f"channel {self.topic} closed")
            self.rejoin_timer.reset()
            self.state = ChannelStates.CLOSED
            self.socket._remove(self)

        def on_error(payload, *args):
            if self.is_leaving or self.is_closed:
                return

            logging.info(f"channel {self.topic} error: {payload}")
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
    def subscribe(
        self,
        callback: Optional[
            Callable[[RealtimeSubscribeStates, Optional[Exception]], None]
        ] = None,
    ) -> SyncRealtimeChannel:
        """
        Subscribe to the channel.

        :return: The Channel instance for method chaining.
        """
        if not self.socket.is_connected:
            self.socket.connect()
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

            def on_join_push_timeout():
                callback and callback(RealtimeSubscribeStates.TIMED_OUT, None)

            self.join_push.receive("ok", on_join_push_ok).receive(
                "error", on_join_push_error
            ).receive("timeout", on_join_push_timeout)

            self._rejoin()

        return self

    def unsubscribe(self):
        self.state = ChannelStates.LEAVING

        self.rejoin_timer.reset()
        self.join_push.destroy()

        def _close(*args):
            logging.info(f"channel {self.topic} leave")
            self._trigger(ChannelEvents.close, "leave")

        leave_push = SyncPush(self, ChannelEvents.leave, {})
        leave_push.receive("ok", _close).receive("timeout", _close)

        leave_push.send()

        if not self._can_push():
            leave_push.trigger("ok", {})

    def push(
        self, event: str, payload: Dict[str, Any], timeout: Optional[int] = None
    ) -> SyncPush:
        if not self._joined_once:
            raise Exception(
                f"tried to push '{event}' to '{self.topic}' before joining. Use channel.subscribe() before pushing events"
            )

        timeout = timeout or self.timeout

        push = SyncPush(self, event, payload, timeout)
        if self._can_push():
            push.send()
        else:
            push.start_timeout()
            self._push_buffer.append(push)

        return push

    def join(self) -> SyncRealtimeChannel:
        """
        Coroutine that attempts to join Phoenix Realtime server via a certain topic.

        :return: Channel
        """
        try:
            self.socket._send(
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

    # Event handling methods
    def _on(
        self, type: str, callback: Callback, filter: Dict[str, Any] = {}
    ) -> SyncRealtimeChannel:
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

    def _off(self, type: str, filter: Dict[str, Any]) -> SyncRealtimeChannel:
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
    ) -> SyncRealtimeChannel:
        """
        Set up a listener for a specific broadcast event.

        :param event: The name of the broadcast event to listen for.
        :param callback: The callback function to execute when the event is received.
        :return: The Channel instance for method chaining.
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
    ) -> SyncRealtimeChannel:
        """
        Set up a listener for a specific Postgres changes event.

        :param event: The name of the Postgres changes event to listen for.
        :param table: The table name for which changes should be monitored.
        :param callback: The callback function to execute when the event is received.
        :param schema: The database schema where the table exists. Default is 'public'.
        :return: The Channel instance for method chaining.
        """

        binding_filter = {"event": event, "schema": schema, "table": table}
        if filter:
            binding_filter["filter"] = filter

        return self._on(
            "postgres_changes",
            filter=binding_filter,
            callback=lambda payload, _: callback(payload),
        )

    # Presence methods
    def track(self, user_status: Dict[str, Any]) -> None:
        """
        Track a user's presence.

        :param user_status: User's presence status.
        :return: None
        """
        self.send_presence("track", user_status)

    def untrack(self) -> None:
        """
        Untrack a user's presence.

        :return: None
        """
        self.send_presence("untrack", {})

    def presence_state(self) -> RealtimePresenceState:
        return self.presence.state

    def on_presence_sync(self, callback: Callable[[], None]) -> SyncRealtimeChannel:
        """
        Register a callback for presence sync events.

        :param callback: The callback function to execute when a presence sync event occurs.
        :return: The Channel instance for method chaining.
        """
        self.presence.on_sync(callback)
        return self

    def on_presence_join(self, callback: PresenceOnJoinCallback) -> SyncRealtimeChannel:
        """
        Register a callback for presence join events.

        :param callback: The callback function to execute when a presence join event occurs.
        :return: The Channel instance for method chaining.
        """
        self.presence.on_join(callback)
        return self

    def on_presence_leave(
        self, callback: PresenceOnLeaveCallback
    ) -> SyncRealtimeChannel:
        """
        Register a callback for presence leave events.

        :param callback: The callback function to execute when a presence leave event occurs.
        :return: The Channel instance for method chaining.
        """
        self.presence.on_leave(callback)
        return self

    # Broadcast methods
    def send_broadcast(self, event: str, data: Any) -> None:
        """
        Sends a broadcast message to the current channel.

        :param event: The name of the broadcast event.
        :param data: The data to be sent with the message.
        :return: An asyncio.Future object representing the send operation.
        """
        self.push(
            ChannelEvents.broadcast,
            {"type": "broadcast", "event": event, "payload": data},
        )

    # Internal methods
    def _broadcast_endpoint_url(self):
        return f"{http_endpoint_url(self.socket.http_endpoint)}/api/broadcast"

    def _rejoin(self) -> None:
        if self.is_leaving:
            return
        self.socket._leave_open_topic(self.topic)
        self.state = ChannelStates.JOINING
        self.join_push.resend()

    def _can_push(self):
        return self.socket.is_connected and self._joined_once

    def send_presence(self, event: str, data: Any) -> None:
        self.push(ChannelEvents.presence, {"event": event, "payload": data})

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

    def _rejoin_until_connected(self):
        self.rejoin_timer.schedule_timeout()
        if self.socket.is_connected:
            self._rejoin()
