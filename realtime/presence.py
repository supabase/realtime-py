"""
 Defines the RealtimePresence class and its dependencies.
"""

from typing import Any, Callable, Dict, List, Optional


class Presence:
    def __init__(self, presence_ref: str, payload: Dict[str, Any]):
        self.presence_ref = presence_ref
        self.payload = payload


class PresenceOpts:
    def __init__(self, events: "PresenceEvents"):
        self.events = events


class PresenceEvents:
    def __init__(self, state: str, diff: str):
        self.state = state
        self.diff = diff


class RealtimePresence:
    def __init__(self, channel, opts: Optional[PresenceOpts] = None):
        self.channel = channel
        self.state = {}
        self.pending_diffs = []
        self.join_ref = None
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

    def on_join(self, callback: Callable[[str, List[Any], List[Any]], None]):
        self.caller["onJoin"] = callback

    def on_leave(self, callback: Callable[[str, List[Any], List[Any]], None]):
        self.caller["onLeave"] = callback

    def on_sync(self, callback: Callable[[], None]):
        self.caller["onSync"] = callback

    def on_auth_success(self, callback: Callable[[], None]):
        self.caller["onAuthSuccess"] = callback

    def on_auth_failure(self, callback: Callable[[], None]):
        self.caller["onAuthFailure"] = callback

    def _on_state_event(self, payload: Dict[str, Any]):
        self.state = self._sync_state(self.state, payload)
        for diff in self.pending_diffs:
            self.state = self._sync_diff(self.state, diff)
        self.pending_diffs = []
        self.caller["onSync"]()

    def _on_diff_event(self, event: str, payload: Dict[str, Any]):
        if self.in_pending_sync_state():
            self.pending_diffs.append(payload)
        else:
            self.state = self._sync_diff(self.state, payload)
            self.caller["onSync"]()

    def _on_auth_event(self, event: str, payload: Dict[str, Any]):
        if payload.get("status") == "ok":
            self.caller["onAuthSuccess"]()
        else:
            self.caller["onAuthFailure"]()

    def _sync_state(
        self, current_state: Dict[str, Any], new_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Merges the new state into the current state
        current_state |= new_state
        return current_state

    def _sync_diff(self, state: Dict[str, Any], diff: Dict[str, Any]) -> Dict[str, Any]:
        # Applies the diff to the state
        for key, value in diff.items():
            if value is None:
                # If the value in the diff is None, remove the key from the state
                state.pop(key, None)
            else:
                # Otherwise, update or add the key-value pair in the state
                state[key] = value
        return state

    def in_pending_sync_state(self) -> bool:
        return self.join_ref is None or self.join_ref != self.channel.join_ref
