"""
 Defines the RealtimePresence class and its dependencies.
"""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

type PresenceOnJoinCallback = Callable[[str, List[Any], List[Any]], None]
type PresenceOnLeaveCallback = Callable[[str, List[Any], List[Any]], None]

from typing import Dict, List, Literal, TypeVar

T = TypeVar("T", bound=Dict[str, Any])


class Presence(Dict[str, Any]):
    presence_ref: str


RealtimePresenceState = Dict[str, List[Presence[T]]]


class RealtimePresenceListenEvents(str, Enum):
    SYNC = "SYNC"
    JOIN = "JOIN"
    LEAVE = "LEAVE"


class RealtimePresenceJoinPayload(Dict[str, Any]):
    event: Literal[RealtimePresenceListenEvents.JOIN]
    key: str
    current_presences: List[Presence[T]]
    new_presences: List[Presence[T]]


class RealtimePresenceLeavePayload(Dict[str, Any]):
    event: Literal[RealtimePresenceListenEvents.LEAVE]
    key: str
    current_presences: List[Presence[T]]
    left_presences: List[Presence[T]]


from typing import Any, Callable, Dict, List, TypedDict


class PresenceMeta(TypedDict, total=False):
    phx_ref: str
    phx_ref_prev: str


class RawPresenceStateEntry(TypedDict):
    metas: List[PresenceMeta]


RawPresenceState = Dict[str, RawPresenceStateEntry]


class RawPresenceDiff(TypedDict):
    joins: RawPresenceState
    leaves: RawPresenceState


class PresenceDiff(TypedDict):
    joins: RealtimePresenceState
    leaves: RealtimePresenceState


PresenceChooser = Callable[[str, List[Presence[T]]], T]


class PresenceEvents:
    def __init__(self, state: str, diff: str):
        self.state = state
        self.diff = diff


class PresenceOpts:
    def __init__(self, events: PresenceEvents):
        self.events = events


class RealtimePresence:
    def __init__(self, channel, opts: Optional[PresenceOpts] = None):
        self.channel = channel
        self.state: RealtimePresenceState = {}
        self.pending_diffs: List[RawPresenceDiff] = []
        self.join_ref: Optional[str] = None
        self.caller = {
            "onJoin": lambda *args: None,
            "onLeave": lambda *args: None,
            "onSync": lambda: None,
            "onAuthSuccess": lambda: None,
            "onAuthFailure": lambda: None,
        }
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
        self.caller["onJoin"] = callback

    def on_leave(self, callback: PresenceOnLeaveCallback):
        self.caller["onLeave"] = callback

    def on_sync(self, callback: Callable[[], None]):
        self.caller["onSync"] = callback

    def on_auth_success(self, callback: Callable[[], None]):
        self.caller["onAuthSuccess"] = callback

    def on_auth_failure(self, callback: Callable[[], None]):
        self.caller["onAuthFailure"] = callback

    def _on_state_event(self, payload: RawPresenceState, **kwargs):
        onJoin = self.caller["onJoin"]
        onLeave = self.caller["onLeave"]
        onSync = self.caller["onSync"]

        self.join_ref = self.channel.join_ref
        self.state = self._sync_state(self.state, payload, onJoin, onLeave)

        for diff in self.pending_diffs:
            self.state = self._sync_diff(self.state, diff, onJoin, onLeave)
        self.pending_diffs = []
        onSync()

    def _on_diff_event(self, payload: Dict[str, Any], **kwargs):
        onJoin = self.caller["onJoin"]
        onLeave = self.caller["onLeave"]
        onSync = self.caller["onSync"]

        if self.in_pending_sync_state():
            self.pending_diffs.append(payload)
        else:
            self.state = self._sync_diff(self.state, payload, onJoin, onLeave)
            onSync()

    def _on_auth_event(self, payload: Dict[str, Any], **kwargs):
        if payload.get("status") == "ok":
            self.caller["onAuthSuccess"]()
        else:
            self.caller["onAuthFailure"]()

    def _sync_state(
        self,
        current_state: RealtimePresenceState,
        new_state: Union[RawPresenceState, RealtimePresenceState],
        onJoin: PresenceOnJoinCallback,
        onLeave: PresenceOnLeaveCallback,
    ) -> RealtimePresenceState:
        state = {key: list(value) for key, value in current_state.items()}
        transformed_state = RealtimePresence._transform_state(new_state)

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

        return self._sync_diff(
            state, {"joins": joins, "leaves": leaves}, onJoin, onLeave
        )

    def _sync_diff(
        self,
        state: RealtimePresenceState,
        diff: Union[RawPresenceDiff, PresenceDiff],
        onJoin: PresenceOnJoinCallback,
        onLeave: PresenceOnLeaveCallback,
    ) -> RealtimePresenceState:
        joins = RealtimePresence._transform_state(diff.get("joins", {}))
        leaves = RealtimePresence._transform_state(diff.get("leaves", {}))

        for key, new_presences in joins.items():
            current_presences = state.get(key, [])
            state[key] = new_presences

            if len(current_presences) > 0:
                joined_presence_refs = {
                    presence.get("presence_ref") for presence in state.get(key)
                }
                cur_presences = list(
                    presence
                    for presence in current_presences
                    if presence.get("presence_ref") not in joined_presence_refs
                )
                state[key] = cur_presences + state[key]

            onJoin(key, current_presences, new_presences)

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

            onLeave(key, current_presences, left_presences)

            if len(current_presences) == 0:
                del state[key]

        return state

    def in_pending_sync_state(self) -> bool:
        return self.join_ref is None or self.join_ref != self.channel.join_ref

    def _transform_state(
        state: Union[RawPresenceState, RealtimePresenceState]
    ) -> RealtimePresenceState:
        """
        Transform the raw presence state into a standardized RealtimePresenceState format.

        This method processes the input state, which can be either a RawPresenceState or
        an already transformed RealtimePresenceState. It handles the conversion of the
        Phoenix channel's presence format to our internal representation.

        Args:
            state (Union[RawPresenceState, RealtimePresenceState]): The presence state to transform.

        Returns:
            RealtimePresenceState: The transformed presence state.

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
                    presence["presence_ref"] = presence.pop("phx_ref", None)
                    presence.pop("phx_ref_prev", None)
                    new_state[key].append(presence)

            else:
                new_state[key] = presences
        return new_state
