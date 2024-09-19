import asyncio
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

from realtime._async.presence import AsyncRealtimePresence
from realtime._async.push import AsyncPush
from realtime._async.timer import AsyncTimer
from realtime.exceptions import RealtimeError
from realtime.types import (
    Binding,
    ChannelEvents,
    ChannelStates,
    EventCallback,
    PresenceOnJoinCallback,
    PresenceOnLeaveCallback,
    RealtimeChannelConfig,
    RealtimePostgresChangesListenEvent,
    RealtimeSubscribeStates,
)

if TYPE_CHECKING:
    from realtime._async.client import AsyncRealtimeClient

logger = logging.getLogger(__name__)


class AsyncRealtimeChannel:
    """Manages communication over a specific topic in the WebSocket connection."""

    def __init__(
        self,
        socket: "AsyncRealtimeClient",
        topic: str,
        params: Optional[RealtimeChannelConfig] = None,
    ) -> None:
        """
        Initialize the AsyncRealtimeChannel.

        Args:
            socket (AsyncRealtimeClient): The parent socket client.
            topic (str): The topic string, typically in the format 'realtime:<identifier>'.
            params (Optional[RealtimeChannelConfig]): Optional configuration parameters for the channel.
        """
        self.socket = socket
        self.topic = topic
        self.params = params or {}
        self.state: ChannelStates = ChannelStates.CLOSED
        self.join_ref: Optional[str] = None
        self._bindings: Dict[str, List[Binding]] = {}
        self._push_buffer: List[AsyncPush] = []
        self._join_push: Optional[AsyncPush] = None
        self._rejoin_timer: AsyncTimer = AsyncTimer(
            self._attempt_rejoin, self._calculate_rejoin_delay
        )
        self.presence = AsyncRealtimePresence(self)
        # Store subscription IDs assigned by the server
        self._postgres_changes_ids: List[int] = []
        # Store postgres_changes subscriptions
        self._postgres_changes_subscriptions: List[Dict[str, Any]] = []
        self.auto_rejoin: bool = True
        # Register reply handler
        self.on(ChannelEvents.REPLY.value, self._handle_reply)

    @property
    def is_joined(self) -> bool:
        """Check if the channel is in the 'joined' state."""
        return self.state == ChannelStates.JOINED

    @property
    def is_joining(self) -> bool:
        """Check if the channel is in the 'joining' state."""
        return self.state == ChannelStates.JOINING

    async def subscribe(
        self,
        callback: Optional[
            Callable[[RealtimeSubscribeStates, Optional[Exception]], Awaitable[None]]
        ] = None,
    ) -> "AsyncRealtimeChannel":
        """
        Subscribes to the channel.

        Args:
            callback (Optional[Callable[[RealtimeSubscribeStates, Optional[Exception]], None]]): Optional callback invoked with subscription status.

        Returns:
            AsyncRealtimeChannel: Self, to allow method chaining.
        """
        if self.is_joined:
            logger.warning("Already joined channel.")
            if callback:
                await callback(RealtimeSubscribeStates.SUBSCRIBED, None)
            return self

        # Set state before any await
        self.state = ChannelStates.JOINING

        if not self.socket.is_connected:
            await self.socket.connect()

        # Build the config
        config = self.params.get("config", {})
        # Include postgres_changes subscriptions collected
        if self._postgres_changes_subscriptions:
            config["postgres_changes"] = self._postgres_changes_subscriptions

        # Prepare the payload according to the protocol
        payload = {"config": config}

        # Include the access token if present
        if self.socket.access_token:
            payload["access_token"] = self.socket.access_token

        # Create the join push with the payload
        self._join_push = AsyncPush(
            self, ChannelEvents.JOIN.value, payload, self.socket.timeout
        )
        self.join_ref = self._join_push._ref

        # Register callbacks before sending
        async def on_success(join_payload: Dict[str, Any], ref: Optional[str]) -> None:
            # Modify shared state inside callback
            self.state = ChannelStates.JOINED
            self._flush_push_buffer()
            # Parse 'postgres_changes' IDs from server response
            response = join_payload.get("response", {})
            postgres_changes = response.get("postgres_changes", [])
            self._postgres_changes_ids = [change["id"] for change in postgres_changes]
            if callback:
                await callback(RealtimeSubscribeStates.SUBSCRIBED, None)

        async def on_error(join_payload: Dict[str, Any], ref: Optional[str]) -> None:
            self.state = ChannelStates.ERRORED
            error = RealtimeError(f"Failed to join channel: {join_payload}")
            logger.error(f"Channel subscription error: {error}")
            if callback:
                await callback(RealtimeSubscribeStates.CHANNEL_ERROR, error)

        async def on_timeout(join_payload: Dict[str, Any], ref: Optional[str]) -> None:
            self.state = ChannelStates.ERRORED
            logger.warning(f"Channel subscription timed out: {self.topic}")
            if callback:
                await callback(RealtimeSubscribeStates.TIMED_OUT, None)

        self._join_push.receive("ok", on_success)
        self._join_push.receive("error", on_error)
        self._join_push.receive("timeout", on_timeout)

        await self._join_push.send()

        return self

    async def unsubscribe(self) -> None:
        """Unsubscribes from the channel."""
        if self.state != ChannelStates.JOINED:
            return
        self.state = ChannelStates.LEAVING
        leave_push = AsyncPush(self, ChannelEvents.LEAVE.value, {}, self.socket.timeout)
        await leave_push.send()
        self.state = ChannelStates.LEFT
        logger.info(f"Unsubscribed from channel: {self.topic}")

    async def _attempt_rejoin(self) -> None:
        """Attempts to rejoin the channel."""
        if self.is_joined or self.is_joining:
            return
        logger.info(f"Attempting to rejoin channel: {self.topic}")
        await self.subscribe()

    def _calculate_rejoin_delay(self, tries: int) -> float:
        """Calculates the delay before rejoining."""
        return min(self.socket.initial_backoff * (2 ** (tries - 1)), 30.0)

    def _flush_push_buffer(self) -> None:
        """Sends any pushes that were buffered before the channel was joined."""
        while self._push_buffer:
            push = self._push_buffer.pop(0)
            asyncio.create_task(push.send())

    async def _on_error(self, error: Exception) -> None:
        """Handles channel errors."""
        logger.exception(f"Channel error on topic '{self.topic}': {error}")
        self.state = ChannelStates.ERRORED
        if self.auto_rejoin:
            self._rejoin_timer.reset()
            self._rejoin_timer.schedule()

    async def _on_disconnect(self) -> None:
        """Resets the channel state upon socket disconnection."""
        logger.debug(f"Channel '{self.topic}' is resetting state due to disconnection.")
        self.state = ChannelStates.CLOSED
        self.join_ref = None
        if self.auto_rejoin:
            self._rejoin_timer.reset()
            self._rejoin_timer.schedule()

    def _reply_event_name(self, ref: Optional[str]) -> str:
        """Generates the event name for replies."""
        return f"chan_reply_{ref}"

    def on(self, event: str, callback: EventCallback) -> None:
        """
        Registers a callback for a specific event.

        Args:
            event (str): The event name.
            callback (EventCallback): The callback function.
        """
        if not asyncio.iscoroutinefunction(callback):
            raise ValueError("Callback must be an async function.")
        event = event.lower()
        bindings = self._bindings.setdefault(event, [])
        binding = Binding(event_type=event, callback=callback, filter={})
        bindings.append(binding)

    def off(self, event: str, callback: EventCallback) -> None:
        """
        Unregisters a callback for a specific event.

        Args:
            event (str): The event name.
            callback (EventCallback): The callback function to remove.
        """
        event = event.lower()
        bindings = self._bindings.get(event, [])
        self._bindings[event] = [b for b in bindings if b.callback != callback]

    def off_all(self, event: str) -> None:
        """
        Unregisters all callbacks for a specific event.

        Args:
            event (str): The event name.
        """
        event = event.lower()
        if event in self._bindings:
            del self._bindings[event]

    async def _trigger(
        self, event: str, payload: Optional[Any], ref: Optional[str] = None
    ) -> None:
        """Triggers callbacks registered for an event."""
        bindings = self._bindings.get(event.lower(), [])
        for binding in bindings:
            try:
                await binding.callback(payload, ref)
            except Exception as e:
                logger.exception(f"Exception in callback for event '{event}': {e}")

    async def send_broadcast(self, event: str, payload: Dict[str, Any]) -> None:
        """
        Sends a broadcast message through the channel.

        Args:
            event (str): The event name for the broadcast.
            payload (Dict[str, Any]): The payload to send.
        """
        if not self.is_joined:
            logger.warning("Cannot send broadcast, channel not joined.")
            return

        message = {"type": "broadcast", "event": event, "payload": payload}
        broadcast_push = AsyncPush(
            self, ChannelEvents.BROADCAST.value, message, self.socket.timeout
        )
        await broadcast_push.send()
        logger.debug(f"Broadcast message sent on channel '{self.topic}': {message}")

    async def update_access_token(self, token: Optional[str]) -> None:
        """
        Updates the access token for the channel.

        Args:
            token (Optional[str]): The new access token.
        """
        if self.state != ChannelStates.JOINED:
            return
        access_token_push = AsyncPush(
            self,
            ChannelEvents.ACCESS_TOKEN.value,
            {"access_token": token},
            self.socket.timeout,
        )
        await access_token_push.send()
        logger.info(f"Access token updated for channel '{self.topic}'")

    def on_broadcast(self, event: str, callback: EventCallback) -> None:
        """
        Registers a callback for broadcast events with a specific event type.

        Args:
            event (str): The specific event name to listen for within broadcast events.
            callback (EventCallback): The callback function.
        """
        if not asyncio.iscoroutinefunction(callback):
            raise ValueError("Callback must be an async function.")

        # Define a wrapper callback that filters events
        async def broadcast_callback(
            payload: Dict[str, Any], ref: Optional[str]
        ) -> None:
            if payload.get("event") == event:
                await callback(payload.get("payload", {}), ref)

        # Register the wrapper callback for 'broadcast' events
        self.on(ChannelEvents.BROADCAST.value.lower(), broadcast_callback)

    def on_postgres_changes(
        self,
        event: RealtimePostgresChangesListenEvent,
        callback: EventCallback,
        schema: str = "public",
        table: str = "*",
        filter: Optional[str] = None,
    ) -> "AsyncRealtimeChannel":
        """
        Subscribes to Postgres changes and registers a callback.

        Args:
            event (RealtimePostgresChangesListenEvent): The Postgres event to listen for.
            callback (EventCallback): The callback function.
            schema (str): The database schema.
            table (str): The table to listen to.
            filter (Optional[str]): Optional filter expression.

        Returns:
            AsyncRealtimeChannel: Self, to allow method chaining.
        """
        if not asyncio.iscoroutinefunction(callback):
            raise ValueError("Callback must be an async function.")

        # Append the subscription parameters
        subscription = {"event": event, "schema": schema, "table": table}
        if filter is not None:
            subscription["filter"] = filter

        self._postgres_changes_subscriptions.append(subscription)

        # Register the callback for the 'postgres_changes' event
        self.on("postgres_changes", callback)

        return self

    async def _handle_reply(self, payload: Dict[str, Any], ref: Optional[str]) -> None:
        """Handles replies from the server."""
        event_name = self._reply_event_name(ref)
        await self._trigger(event_name, payload, ref)

    def on_presence_sync(
        self, callback: Callable[[], Awaitable[None]]
    ) -> "AsyncRealtimeChannel":
        """
        Registers a coroutine callback for presence synchronization events.
        """
        self.presence.on_sync(callback)
        return self

    def on_presence_join(
        self, callback: PresenceOnJoinCallback
    ) -> "AsyncRealtimeChannel":
        """
        Registers a coroutine callback for when new presences join.
        """
        self.presence.on_join(callback)
        return self

    def on_presence_leave(
        self, callback: PresenceOnLeaveCallback
    ) -> "AsyncRealtimeChannel":
        """
        Registers a coroutine callback for when presences leave.
        """
        self.presence.on_leave(callback)
        return self

    async def track(self, payload: Dict[str, Any]) -> None:
        """
        Tracks a user's presence in the channel.
        """
        if not self.is_joined:
            raise RealtimeError("Cannot track presence before joining the channel.")

        message = {"event": "track", "payload": payload}
        presence_push = AsyncPush(
            self,
            ChannelEvents.PRESENCE.value,
            message,
            self.socket.timeout,
        )
        await presence_push.send()

    async def untrack(self) -> None:
        """
        Stops tracking a user's presence in the channel.
        """
        if not self.is_joined:
            raise RealtimeError("Cannot untrack presence before joining the channel.")

        message = {"event": "untrack", "payload": {}}
        presence_push = AsyncPush(
            self,
            ChannelEvents.PRESENCE.value,
            message,
            self.socket.timeout,
        )
        await presence_push.send()
