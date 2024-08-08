from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, NamedTuple, Optional

from realtime.message import ChannelEvents
from realtime.types import Callback

from .presence import RealtimePresence
from .transformers import http_endpoint_url

if TYPE_CHECKING:
    from realtime.connection import Socket


class CallbackListener(NamedTuple):
    """A tuple with `event` and `callback`"""

    event: str
    on_params: Dict[str, Any]
    callback: Callback


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


class Push:
    def __init__(self, channel: Channel, event: str, payload: Dict[str, Any] = {}):
        self.channel = channel
        self.event = event
        self.payload = payload
        self.ref = channel.socket._make_ref()

    async def send(self):
        self.ref = self.channel.socket._make_ref()

        message = {
            "topic": self.channel.topic,
            "event": self.event,
            "payload": self.payload,
            "ref": self.ref,
        }

        try:
            await self.channel.socket.send(message)
        except Exception as e:
            logging.error(f"send push failed: {e}")

    def update_payload(self, payload: Dict[str, Any]):
        self.payload = {**self.payload, **payload}


class Channel:
    """
    `Channel` is an abstraction for a topic listener for an existing socket connection.
    Each Channel has its own topic and a list of event-callbacks that responds to messages.
    Should only be instantiated through `connection.Socket().set_channel(topic)`
    Topic-Channel has a 1-many relationship.
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
        self.listeners: List[CallbackListener] = []
        self.joined = False
        self.bindings: Dict[str, List[Binding]] = {}
        self.presence = RealtimePresence(self)
        self.filter = None
        self.current_event = None
        self.join_ref: Optional[int] = None

        self.params["config"] = {
            "broadcast": {"ack": False, "self": False},
            "presence": {"key": ""},
            "private": False,
            **params.get("config", {}),
        }

        self.broadcast_endpoint_url = self._broadcast_endpoint_url()

    def _broadcast_endpoint_url(self):
        return f"{http_endpoint_url(self.socket.http_endpoint)}/api/broadcast"

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

    async def subscribe(self) -> Channel:
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
            self.joined = True
            await self.rejoin()
            if len(self.listeners) == 0:
                cl = CallbackListener("subscribed", on_params={}, callback=None)
                self.listeners.append(cl)
        return self

    async def rejoin(self) -> None:
        """
        Rejoin the channel.

        :return: None
        """
        if not self.joined:
            return

        if self.current_event == "postgres_changes" and self.filter:
            self.channel_params["filter"] = self.filter

        params = self.params
        postgres_changes = [
            binding.filter for binding in self.bindings.get("postgres_changes", [])
        ]

        params["config"].setdefault("postgres_changes", []).extend(postgres_changes)

        if self.socket.access_token:
            params["access_token"] = self.socket.access_token

        await self.push(ChannelEvents.join, params)

    async def push(self, event: str, payload: Dict[str, Any]) -> Push:
        if not self.joined:
            raise Exception(
                f"tried to push '{event}' to '{self.topic}' before joining. Use channel.subscribe() before pushing events"
            )

        push = Push(self, event, payload)
        await push.send()
        return push

    # @Deprecated:
    # You should use `subscribe` instead of this low-level method. It will be removed in the future.
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

    def track(self, user_status: Dict[str, Any]) -> None:
        """
        Track a user's presence.

        :param user_status: User's presence status.
        :return: None
        """
        self.presence.track(user_status)

    def untrack(self) -> None:
        """
        Untrack a user's presence.

        :return: None
        """
        self.presence.untrack()

    def on_presence_sync(self, callback: Callback) -> Channel:
        """
        Register a callback for presence sync events.

        :param callback: The callback function to execute when a presence sync event occurs.
        :return: The Channel instance for method chaining.
        """
        self.presence.on_sync(callback)
        return self

    def on_presence_join(self, callback: Callback) -> Channel:
        """
        Register a callback for presence join events.

        :param callback: The callback function to execute when a presence join event occurs.
        :return: The Channel instance for method chaining.
        """
        self.presence.on_join(callback)
        return self

    def on_presence_leave(self, callback: Callback) -> Channel:
        """
        Register a callback for presence leave events.

        :param callback: The callback function to execute when a presence leave event occurs.
        :return: The Channel instance for method chaining.
        """
        self.presence.on_leave(callback)
        return self

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

    def _trigger(self, type: str, payload, ref: Optional[str]):
        type_lowercase = type.lower()
        events = [
            ChannelEvents.close,
            ChannelEvents.error,
            ChannelEvents.leave,
            ChannelEvents.join,
        ]

        if ref is not None and type_lowercase in events and ref != self.join_ref:
            return

        bindings = self.bindings.get(type_lowercase, [])
        if type_lowercase in ["insert", "update", "delete"]:
            bindings = self.bindings.get("postgres_changes", [])

        for binding in bindings:
            event = binding.filter.get("event", "").lower()
            if event == "*" or event == type_lowercase:
                if binding.id is None or (binding.id in payload.get("ids", [])):
                    binding.callback(payload)
