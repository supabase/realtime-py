"""
Defines the RealtimePresence class and its dependencies.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Union

from ..types import (
    Presence,
    PresenceDiff,
    PresenceEvents,
    PresenceOnJoinCallback,
    PresenceOnLeaveCallback,
    PresenceOpts,
    RawPresenceDiff,
    RawPresenceState,
    RealtimePresenceState,
)

logger = logging.getLogger(__name__)


class AsyncRealtimePresence:
    def __init__(self, channel, opts: Optional[PresenceOpts] = None):
        self.channel = channel
        self.state: RealtimePresenceState = {}
        self.pending_diffs: List[RawPresenceDiff] = []
        self.join_ref: Optional[str] = None
        self.on_join_callback: Optional[PresenceOnJoinCallback] = None
        self.on_leave_callback: Optional[PresenceOnLeaveCallback] = None
        self.on_sync_callback: Optional[Callable[[], None]] = None
        self.on_auth_success_callback: Optional[Callable[[], None]] = None
        self.on_auth_failure_callback: Optional[Callable[[], None]] = None
        # Initialize with default events if not provided
        events = (
            opts.events
            if opts
            else PresenceEvents(state="presence_state", diff="presence_diff")
        )
        # Set up event listeners for presence state and diff
        self.channel._on(events.state, callback=self._on_state_event)
        self.channel._on(events.diff, callback=self._on_diff_event)
        self.channel._on("phx_auth", callback=self._on_auth_event)

    def on_join(self, callback: PresenceOnJoinCallback):
        self.on_join_callback = callback

    def on_leave(self, callback: PresenceOnLeaveCallback):
        self.on_leave_callback = callback

    def on_sync(self, callback: Callable[[], None]):
        self.on_sync_callback = callback

    def on_auth_success(self, callback: Callable[[], None]):
        self.on_auth_success_callback = callback

    def on_auth_failure(self, callback: Callable[[], None]):
        self.on_auth_failure_callback = callback

    def _on_state_event(self, payload: RawPresenceState, *args):
        self.join_ref = self.channel.join_ref
        self.state = self._sync_state(self.state, payload)

        for diff in self.pending_diffs:
            self.state = self._sync_diff(self.state, diff)
        self.pending_diffs = []
        if self.on_sync_callback:
            self.on_sync_callback()

    def _on_diff_event(self, payload: RawPresenceDiff, *args):
        if self.in_pending_sync_state():
            self.pending_diffs.append(payload)
        else:
            self.state = self._sync_diff(self.state, payload)
            if self.on_sync_callback:
                self.on_sync_callback()

    def _on_auth_event(self, payload: Dict[str, Any], *args):
        if payload.get("status") == "ok":
            if self.on_auth_success_callback:
                self.on_auth_success_callback()
        else:
            if self.on_auth_failure_callback:
                self.on_auth_failure_callback()

    def _sync_state(
        self,
        current_state: RealtimePresenceState,
        new_state: Union[RawPresenceState, RealtimePresenceState],
    ) -> RealtimePresenceState:
        state = {key: list(value) for key, value in current_state.items()}
        transformed_state = AsyncRealtimePresence._transform_state(new_state)

        joins: Dict[str, Any] = {}
        leaves: Dict[str, Any] = {
            k: v for k, v in state.items() if k not in transformed_state
        }

        for key, value in transformed_state.items():
            current_presences = state.get(key, [])

            if len(current_presences) > 0:
                new_presence_refs = {presence.get("presence_ref") for presence in value}
                cur_presence_refs = {
                    presence.get("presence_ref") for presence in current_presences
                }

                joined_presences = [
                    p for p in value if p.get("presence_ref") not in cur_presence_refs
                ]
                left_presences = [
                    p
                    for p in current_presences
                    if p.get("presence_ref") not in new_presence_refs
                ]

                if joined_presences:
                    joins[key] = joined_presences
                if left_presences:
                    leaves[key] = left_presences
            else:
                joins[key] = value

        return self._sync_diff(state, {"joins": joins, "leaves": leaves})

    def _sync_diff(
        self,
        state: RealtimePresenceState,
        diff: Union[RawPresenceDiff, PresenceDiff],
    ) -> RealtimePresenceState:
        joins = AsyncRealtimePresence._transform_state(diff.get("joins", {}))
        leaves = AsyncRealtimePresence._transform_state(diff.get("leaves", {}))

        for key, new_presences in joins.items():
            current_presences = state.get(key, [])
            state[key] = new_presences

            if len(current_presences) > 0:
                joined_presence_refs = {
                    presence.get("presence_ref") for presence in new_presences
                }
                cur_presences = list(
                    presence
                    for presence in current_presences
                    if presence.get("presence_ref") not in joined_presence_refs
                )
                state[key] = cur_presences + state[key]

            if self.on_join_callback:
                self.on_join_callback(key, current_presences, new_presences)

        for key, left_presences in leaves.items():
            current_presences = state.get(key, [])

            if len(current_presences) == 0:
                break

            presence_refs_to_remove = {
                presence.get("presence_ref") for presence in left_presences
            }
            current_presences = [
                presence
                for presence in current_presences
                if presence.get("presence_ref") not in presence_refs_to_remove
            ]
            state[key] = current_presences

            if self.on_leave_callback:
                self.on_leave_callback(key, current_presences, left_presences)

            if len(current_presences) == 0:
                del state[key]

        return state

    def in_pending_sync_state(self) -> bool:
        return self.join_ref is None or self.join_ref != self.channel.join_ref

    @staticmethod
    def _transform_state(
        state: Union[RawPresenceState, RealtimePresenceState],
    ) -> RealtimePresenceState:
        """
        Transform the raw presence state into a standardized RealtimePresenceState format.

        This method processes the input state, which can be either a RawPresenceState or
        an already transformed RealtimePresenceState. It handles the conversion of the
        Phoenix channel's presence format to our internal representation.

        Args:
            state (Union[RawPresenceState, RealtimePresenceState[T]]): The presence state to transform.

        Returns:
            RealtimePresenceState[T]: The transformed presence state.

        Example:
            Input (RawPresenceState):
            {
                "user1": {
                    "metas": [
                        {"phx_ref": "ABC123", "user_id": "user1", "status": "online"},
                        {"phx_ref": "DEF456", "phx_ref_prev": "ABC123", "user_id": "user1", "status": "away"}
                    ]
                },
                "user2": [{"user_id": "user2", "status": "offline"}]
            }

            Output (RealtimePresenceState):
            {
                "user1": [
                    {"presence_ref": "ABC123", "user_id": "user1", "status": "online"},
                    {"presence_ref": "DEF456", "user_id": "user1", "status": "away"}
                ],
                "user2": [{"user_id": "user2", "status": "offline"}]
            }
        """
        new_state: RealtimePresenceState = {}
        for key, presences in state.items():
            if isinstance(presences, dict) and "metas" in presences:
                new_state[key] = []

                for presence in presences["metas"]:
                    if "phx_ref_prev" in presence:
                        del presence["phx_ref_prev"]
                    new_presence: Presence = {"presence_ref": presence.pop("phx_ref")}
                    new_presence.update(presence)
                    new_state[key].append(new_presence)

            else:
                new_state[key] = presences
        return new_state
