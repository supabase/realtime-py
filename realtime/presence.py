"""
 Defines the RealtimePresence class and its dependencies.
"""

from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from .channel import RealtimeChannel


class RealtimePresenceListenEvents(str, Enum):
    SYNC = "sync"
    JOIN = "join"
    LEAVE = "leave"


Presence = Dict[str, Any]
RealtimePresenceState = Dict[str, List[Presence]]
PresenceOnJoinCallback = Callable[[str, List[Presence], List[Presence]], None]
PresenceOnLeaveCallback = Callable[[str, List[Presence], List[Presence]], None]


class RealtimePresence:
    def __init__(
        self, channel: "RealtimeChannel", opts: Optional[Dict[str, Any]] = None
    ):
        self.channel = channel
        self.state: RealtimePresenceState = {}
        self.pending_diffs: List[Dict[str, Any]] = []
        self.join_ref: Optional[str] = None
        self.caller = {
            "onJoin": lambda *args: None,
            "onLeave": lambda *args: None,
            "onSync": lambda: None,
        }

        events = (
            opts.get("events", {"state": "presence_state", "diff": "presence_diff"})
            if opts
            else {"state": "presence_state", "diff": "presence_diff"}
        )

        def on_state(payload: Dict[str, Any]):
            self.join_ref = self.channel._join_ref()
            self.state = self.sync_state(
                self.state, payload, self.caller["onJoin"], self.caller["onLeave"]
            )
            for diff in self.pending_diffs:
                self.state = self.sync_diff(
                    self.state, diff, self.caller["onJoin"], self.caller["onLeave"]
                )
            self.pending_diffs = []
            self.caller["onSync"]()

        def on_diff(payload: Dict[str, Any]):
            if self.in_pending_sync_state():
                self.pending_diffs.append(payload)
            else:
                self.state = self.sync_diff(
                    self.state, payload, self.caller["onJoin"], self.caller["onLeave"]
                )
                self.caller["onSync"]()

        self.channel._on(events["state"], {}, on_state)
        self.channel._on(events["diff"], {}, on_diff)

        self.on_join(
            lambda key, current_presences, new_presences: self.channel._trigger(
                "presence",
                {
                    "event": "join",
                    "key": key,
                    "currentPresences": current_presences,
                    "newPresences": new_presences,
                },
            )
        )

        self.on_leave(
            lambda key, current_presences, left_presences: self.channel._trigger(
                "presence",
                {
                    "event": "leave",
                    "key": key,
                    "currentPresences": current_presences,
                    "leftPresences": left_presences,
                },
            )
        )

        self.on_sync(lambda: self.channel._trigger("presence", {"event": "sync"}))

    @staticmethod
    def sync_state(
        current_state: RealtimePresenceState,
        new_state: Dict[str, Any],
        on_join: PresenceOnJoinCallback,
        on_leave: PresenceOnLeaveCallback,
    ) -> RealtimePresenceState:
        state = current_state.copy()
        transformed_state = RealtimePresence.transform_state(new_state)
        joins: RealtimePresenceState = {}
        leaves: RealtimePresenceState = {}

        for key, presences in state.items():
            if key not in transformed_state:
                leaves[key] = presences

        for key, new_presences in transformed_state.items():
            if key in state:
                current_presences = state[key]
                new_presence_refs = [m["presence_ref"] for m in new_presences]
                cur_presence_refs = [m["presence_ref"] for m in current_presences]
                joined_presences = [
                    m
                    for m in new_presences
                    if m["presence_ref"] not in cur_presence_refs
                ]
                left_presences = [
                    m
                    for m in current_presences
                    if m["presence_ref"] not in new_presence_refs
                ]

                if joined_presences:
                    joins[key] = joined_presences
                if left_presences:
                    leaves[key] = left_presences
            else:
                joins[key] = new_presences

        return RealtimePresence.sync_diff(
            state, {"joins": joins, "leaves": leaves}, on_join, on_leave
        )

    @staticmethod
    def sync_diff(
        state: RealtimePresenceState,
        diff: Dict[str, Any],
        on_join: PresenceOnJoinCallback,
        on_leave: PresenceOnLeaveCallback,
    ) -> RealtimePresenceState:
        joins = RealtimePresence.transform_state(diff.get("joins", {}))
        leaves = RealtimePresence.transform_state(diff.get("leaves", {}))

        for key, new_presences in joins.items():
            current_presences = state.get(key, [])
            state[key] = new_presences.copy()

            if current_presences:
                joined_presence_refs = [m["presence_ref"] for m in state[key]]
                cur_presences = [
                    m
                    for m in current_presences
                    if m["presence_ref"] not in joined_presence_refs
                ]
                state[key] = cur_presences + state[key]

            on_join(key, current_presences, new_presences)

        for key, left_presences in leaves.items():
            current_presences = state.get(key, [])
            if not current_presences:
                continue

            presence_refs_to_remove = [m["presence_ref"] for m in left_presences]
            current_presences = [
                m
                for m in current_presences
                if m["presence_ref"] not in presence_refs_to_remove
            ]

            state[key] = current_presences
            on_leave(key, current_presences, left_presences)

            if not current_presences:
                del state[key]

        return state

    @staticmethod
    def transform_state(state: Dict[str, Any]) -> RealtimePresenceState:
        new_state = {}
        for key, presences in state.items():
            if "metas" in presences:
                new_state[key] = [
                    {**presence, "presence_ref": presence.pop("phx_ref", None)}
                    for presence in presences["metas"]
                    if "phx_ref" in presence
                ]
                for presence in new_state[key]:
                    presence.pop("phx_ref_prev", None)
            else:
                new_state[key] = presences
        return new_state

    def on_join(self, callback: PresenceOnJoinCallback) -> None:
        self.caller["onJoin"] = callback

    def on_leave(self, callback: PresenceOnLeaveCallback) -> None:
        self.caller["onLeave"] = callback

    def on_sync(self, callback: Callable[[], None]) -> None:
        self.caller["onSync"] = callback

    def in_pending_sync_state(self) -> bool:
        return not self.join_ref or self.join_ref != self.channel._join_ref()
