import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..types import DEFAULT_TIMEOUT, Callback, _Hook

if TYPE_CHECKING:
    from .channel import AsyncRealtimeChannel

logger = logging.getLogger(__name__)


class AsyncPush:
    def __init__(
        self,
        channel: "AsyncRealtimeChannel",
        event: str,
        payload: Dict[str, Any] = {},
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.channel = channel
        self.event = event
        self.payload = payload
        self.timeout = timeout
        self.rec_hooks: List[_Hook] = []
        self.ref: Optional[str] = None
        self.ref_event: Optional[str] = None
        self.received_resp: Optional[Dict[str, Any]] = None
        self.sent = False
        self.timeout_task: Optional[asyncio.Task] = None

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
            logger.error(f"send push failed: {e}")

    def update_payload(self, payload: Dict[str, Any]):
        self.payload = {**self.payload, **payload}

    def receive(self, status: str, callback: Callback) -> "AsyncPush":
        if self._has_received(status):
            callback(self.received_resp.get("response", {}))

        self.rec_hooks.append(_Hook(status, callback))
        return self

    def start_timeout(self):
        if self.timeout_task:
            return

        self.ref = self.channel.socket._make_ref()
        self.ref_event = self.channel._reply_event_name(self.ref)

        def on_reply(payload, *args):
            self._cancel_ref_event()
            self._cancel_timeout()
            self.received_resp = payload
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
                hook.callback(response)

    def _has_received(self, status: str):
        return self.received_resp and self.received_resp.get("status") == status
