from __future__ import annotations

import json
import logging
import uuid
from typing import List, TYPE_CHECKING, NamedTuple, Dict, Any

from realtime.message import ChannelEvents
from realtime.types import Callback

if TYPE_CHECKING:
    from realtime.connection import Socket


class CallbackListener(NamedTuple):
    """A tuple with `event` and `callback` """
    event: str
    ref: str
    callback: Callback


class Channel:
    """
    `Channel` is an abstraction for a topic listener for an existing socket connection.
    Each Channel has its own topic and a list of event-callbacks that responds to messages.
    A client can also send messages to a channel and register callback when expecting replies.
    Should only be instantiated through `connection.Socket().set_channel(topic)`
    Topic-Channel has a 1-many relationship.
    """

    def __init__(self, socket: Socket, topic: str, params: Dict[str, Any] = {}) -> None:
        """
        :param socket: Socket object
        :param topic: Topic that it subscribes to on the realtime server
        :param params:
        """
        self.socket = socket
        self.params = params
        self.topic = topic
        self.listeners: List[CallbackListener] = []
        self.joined = False
        self.join_ref = str(uuid.uuid4())
        self.control_msg_ref = ""

    async def join(self) -> None:
        """
        Coroutine that attempts to join Phoenix Realtime server via a certain topic
        :return: None
        """
        if self.socket.version == 1:
            join_req = dict(topic=self.topic, event=ChannelEvents.join,
                            payload={}, ref=None)
        elif self.socket.version == 2:
            # [join_reference, message_reference, topic_name, event_name, payload]
            self.control_msg_ref = str(uuid.uuid4())
            join_req = [self.join_ref, self.control_msg_ref, self.topic, ChannelEvents.join, self.params]

        try:
            await self.socket.ws_connection.send(json.dumps(join_req))
        except Exception as e:
            logging.error(f"Error while joining channel: {str(e)}", exc_info=True)
            return

    async def leave(self) -> None:
        """
        Coroutine that attempts to leave Phoenix Realtime server via a certain topic
        :return: None
        """
        if self.socket.version == 1:
            leave_req = dict(topic=self.topic, event=ChannelEvents.leave,
                             payload={}, ref=None)
        elif self.socket.version == 2:
            leave_req = [self.join_ref, None, self.topic, ChannelEvents.leave, {}]

        try:
            await self.socket.ws_connection.send(json.dumps(leave_req))
        except Exception as e:
            logging.error(f"Error while leaving channel: {str(e)}", exc_info=True)
            return

    def on(self, event: str, ref: str, callback: Callback) -> Channel:
        """
        :param event: A specific event will have a specific callback
        :param ref: A specific reference that will have a specific callback
        :param callback: Callback that takes msg payload as its first argument
        :return: Channel
        """
        cl = CallbackListener(event=event, ref=ref, callback=callback)
        self.listeners.append(cl)
        return self

    def off(self, event: str, ref: str) -> None:
        """
        :param event: Stop responding to a certain event
        :param event: Stop responding to a certain reference
        :return: None
        """
        self.listeners = [
            callback for callback in self.listeners if (callback.event != event and callback.ref != ref)]

    async def send(self, event_name: str, payload: str, ref: str) -> None:
        """
        Coroutine that attempts to join Phoenix Realtime server via a certain topic
        :param event_name: The event_name: it must match the first argument of a handle_in function on the server channel module.
        :param payload: The payload to be sent to the phoenix server
        :param ref: The message reference that the server will use for replying
        :return: None
        """
        if self.socket.version == 1:
            msg = dict(topic=self.topic, event=event_name,
                       payload=payload, ref=None)
        elif self.socket.version == 2:
            msg = [None, ref, self.topic, event_name, payload]

        try:
            await self.socket.ws_connection.send(json.dumps(msg))
        except Exception as e:
            logging.error(f"Error while sending message: {str(e)}", exc_info=True)
            raise
