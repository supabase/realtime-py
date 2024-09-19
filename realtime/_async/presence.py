import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from realtime.types import (
    ChannelEvents,
    Presence,
    PresenceOnJoinCallback,
    PresenceOnLeaveCallback,
    PresenceOpts,
    PresenceStateType,
    RealtimePresenceEvents,
)

if TYPE_CHECKING:
    from realtime._async.channel import AsyncRealtimeChannel

logger = logging.getLogger(__name__)


class AsyncRealtimePresence:
    """Manages presence information within a channel."""

    def __init__(
        self,
        channel: "AsyncRealtimeChannel",
        opts: Optional[PresenceOpts] = None,
    ) -> None:
        """
        Initialize the AsyncRealtimePresence.

        Args:
            channel (AsyncRealtimeChannel): The channel associated with the presence.
            opts (Optional[PresenceOpts]): Optional settings for presence.
        """
        self.channel = channel
        self.state: PresenceStateType = {}
        self.pending_diffs: List[Dict[str, Any]] = []
        self.join_ref: Optional[str] = None
        self._callbacks: Dict[str, List[Callable]] = {
            "join": [],
            "leave": [],
            "sync": [],
            "auth_success": [],
            "auth_failure": [],
        }

        # Extract events from opts or use defaults
        events = opts.get("events", {}) if opts else {}
        self.event_presence_state = events.get(
            "state", RealtimePresenceEvents.PRESENCE_STATE.value
        )
        self.event_presence_diff = events.get(
            "diff", RealtimePresenceEvents.PRESENCE_DIFF.value
        )
        self.event_auth = events.get("auth", ChannelEvents.AUTH.value)

        # Register event listeners
        self.channel.on(self.event_presence_state, self._on_presence_state)
        self.channel.on(self.event_presence_diff, self._on_presence_diff)
        self.channel.on(self.event_auth, self._on_auth_event)

    def on_join(self, callback: PresenceOnJoinCallback) -> None:
        """
        Registers a callback for presence join events.

        Args:
            callback (PresenceOnJoinCallback): The callback function.
        """
        if not asyncio.iscoroutinefunction(callback):
            raise ValueError("Callback must be an async function.")
        self._callbacks["join"].append(callback)

    def on_leave(self, callback: PresenceOnLeaveCallback) -> None:
        """
        Registers a callback for presence leave events.

        Args:
            callback (PresenceOnLeaveCallback): The callback function.
        """
        if not asyncio.iscoroutinefunction(callback):
            raise ValueError("Callback must be an async function.")
        self._callbacks["leave"].append(callback)

    def on_sync(self, callback: Callable[[], Any]) -> None:
        """
        Registers a callback for presence synchronization events.

        Args:
            callback (Callable[[], Any]): The callback function.
        """
        if not asyncio.iscoroutinefunction(callback):
            raise ValueError("Callback must be an async function.")
        self._callbacks["sync"].append(callback)

    def on_auth_success(self, callback: Callable[[], Any]) -> None:
        """
        Registers a callback for authentication success events.

        Args:
            callback (Callable[[], Any]): The callback function.
        """
        if not asyncio.iscoroutinefunction(callback):
            raise ValueError("Callback must be an async function.")
        self._callbacks["auth_success"].append(callback)

    def on_auth_failure(self, callback: Callable[[], Any]) -> None:
        """
        Registers a callback for authentication failure events.

        Args:
            callback (Callable[[], Any]): The callback function.
        """
        if not asyncio.iscoroutinefunction(callback):
            raise ValueError("Callback must be an async function.")
        self._callbacks["auth_failure"].append(callback)

    async def _on_presence_state(
        self, payload: Dict[str, Any], ref: Optional[str]
    ) -> None:
        """Handles the initial presence state."""
        self.join_ref = self.channel.join_ref
        self.state = await self._sync_state({}, payload)

        # Apply pending diffs
        for diff in self.pending_diffs:
            self.state = await self._sync_diff(self.state, diff)
        self.pending_diffs = []
        await self._trigger_sync_callbacks()

    async def _on_presence_diff(
        self, payload: Dict[str, Any], ref: Optional[str]
    ) -> None:
        """Handles presence diffs."""
        if self.in_pending_sync_state():
            self.pending_diffs.append(payload)
        else:
            self.state = await self._sync_diff(self.state, payload)
            await self._trigger_sync_callbacks()

    async def _on_auth_event(self, payload: Dict[str, Any], ref: Optional[str]) -> None:
        """Handles authentication events."""
        status = payload.get("status")
        if status == "ok":
            for callback in self._callbacks["auth_success"]:
                try:
                    await callback()
                except Exception as e:
                    logger.exception(f"Exception in auth success callback: {e}")
        else:
            for callback in self._callbacks["auth_failure"]:
                try:
                    await callback()
                except Exception as e:
                    logger.exception(f"Exception in auth failure callback: {e}")

    async def _trigger_sync_callbacks(self) -> None:
        """Triggers registered sync callbacks."""
        for callback in self._callbacks["sync"]:
            try:
                await callback()
            except Exception as e:
                logger.exception(f"Exception in presence sync callback: {e}")

    async def _sync_state(
        self, current_state: PresenceStateType, new_state: Dict[str, Any]
    ) -> PresenceStateType:
        """Synchronizes the current presence state with the new state received from the server."""
        # Transform the new presence data into Presence instances
        transformed_new_state = self._transform_state(new_state)

        # Will hold the updated state after synchronization
        state: PresenceStateType = {}

        # Diffs to hold joins and leaves
        joins: Dict[str, List[Presence]] = {}
        leaves: Dict[str, List[Presence]] = {}

        # Get sets of all keys (presence keys) from current and new state
        current_keys = set(current_state.keys())
        new_keys = set(transformed_new_state.keys())

        # Calculate leaves (keys present in current state but not in new state)
        for key in current_keys - new_keys:
            leaves[key] = current_state[key]

        # Calculate joins (keys present in new state but not in current state)
        for key in new_keys - current_keys:
            joins[key] = transformed_new_state[key]

        # For keys present in both current and new state, compare presence refs
        for key in current_keys & new_keys:
            current_presences = current_state[key]
            new_presences = transformed_new_state[key]

            # Build sets of phx_refs for quick lookup
            current_refs = {presence.phx_ref for presence in current_presences}
            new_refs = {presence.phx_ref for presence in new_presences}

            # Presences that have joined
            joined_presences = [
                presence
                for presence in new_presences
                if presence.phx_ref not in current_refs
            ]
            if joined_presences:
                joins[key] = joined_presences

            # Presences that have left
            left_presences = [
                presence
                for presence in current_presences
                if presence.phx_ref not in new_refs
            ]
            if left_presences:
                leaves[key] = left_presences

        # Update the state with new presences
        # For all keys, the presences are replaced with the ones from new state
        state.update(transformed_new_state)

        # Build the diff dictionary
        diff = {"joins": joins, "leaves": leaves}

        # Apply the diff (this will trigger callbacks)
        await self._apply_diff(state, diff)

        return state

    async def _sync_diff(
        self, current_state: PresenceStateType, diff: Dict[str, Any]
    ) -> PresenceStateType:
        """Applies diffs to the presence state."""
        state = current_state.copy()
        joins_raw: Dict[str, Any] = diff.get("joins", {})
        leaves_raw: Dict[str, Any] = diff.get("leaves", {})

        # Transform joins and leaves into Presence instances
        joins = self._transform_state(joins_raw)
        leaves = self._transform_state(leaves_raw)

        # Build the diff with transformed joins and leaves
        diff_transformed = {"joins": joins, "leaves": leaves}

        # Apply the diff
        await self._apply_diff(state, diff_transformed)

        return state

    async def _apply_diff(self, state: PresenceStateType, diff: Dict[str, Any]) -> None:
        """Applies the transformed diff to the state and triggers callbacks."""
        joins: Dict[str, List[Presence]] = diff.get("joins", {})
        leaves: Dict[str, List[Presence]] = diff.get("leaves", {})

        # Handle joins
        for key, new_presences in joins.items():
            current_presences = state.get(key, [])
            state[key] = current_presences + new_presences

            # Trigger on_join callbacks
            for callback in self._callbacks["join"]:
                try:
                    await callback(key, current_presences.copy(), new_presences)
                except Exception as e:
                    logger.exception(f"Exception in presence join callback: {e}")

        # Handle leaves
        for key, left_presences in leaves.items():
            current_presences = state.get(key, [])
            left_refs = {p.phx_ref for p in left_presences}

            # Remove left presences
            remaining_presences = [
                p for p in current_presences if p.phx_ref not in left_refs
            ]
            if remaining_presences:
                state[key] = remaining_presences
            else:
                state.pop(key, None)

            # Trigger on_leave callbacks
            for callback in self._callbacks["leave"]:
                try:
                    await callback(key, current_presences.copy(), left_presences)
                except Exception as e:
                    logger.exception(f"Exception in presence leave callback: {e}")

        # Update the internal state
        self.state = state

    def in_pending_sync_state(self) -> bool:
        """Checks if the presence is in a pending sync state."""
        return self.join_ref is None or self.join_ref != self.channel.join_ref

    @staticmethod
    def _transform_state(state: Dict[str, Any]) -> Dict[str, List[Presence]]:
        """Transforms the raw presence state into the expected format."""
        new_state: Dict[str, List[Presence]] = {}
        for key, presences in state.items():
            metas = presences.get("metas", [])
            new_state[key] = []
            for meta in metas:
                phx_ref = meta.get("phx_ref")
                phx_ref_prev = meta.get("phx_ref_prev")
                # Extract metadata excluding 'phx_ref' and 'phx_ref_prev'
                metadata = {
                    k: v
                    for k, v in meta.items()
                    if k not in ["phx_ref", "phx_ref_prev"]
                }
                presence = Presence(
                    phx_ref=phx_ref, phx_ref_prev=phx_ref_prev, metadata=metadata
                )
                new_state[key].append(presence)
        return new_state
