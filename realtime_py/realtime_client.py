from realtime_py.connection import Socket
from realtime_py.constants import TRANSPORT_WEBSOCKET
from realtime_py.serializer import Serializer
from typing import Optional, Dict, Callable
import json


class RealtimeClient:
    def __init__(self, endpoint_url: str, options={}):
        """
        Initializes the socket
        """
        self.endpoint_url = endpoint_url
        # self.decode = lambda payload, callback: Serializer.decode(
        #     payload)
        # TODO: Joel -- Implement the binary string encoder
        self.transport = Socket
        self.options = json.dumps if options.get("encode") == None else None
        self.send_buffer: list[Callable] = []
        self.conn: Optional[Socket] = None

    def connect(self):
        """
        Connects to the socket 
        """
        if self.conn:
            return
        self.conn = self.transport(self.endpoint_url)
        print(self.endpoint_url)
        self.conn.connect()
        if self.conn:
            self.conn.binary_type = 'arraybuffer'
            print("this works kinda")

    def disconnect():
        """
        Disconnects the socket 
        """
        pass

    def log(kind: str, msg: str, data: Optional[any]):
        """
        Logs the message """
        self.logger(kind, msg, data)

    def on_open(callback: Callable):
        # TODO: Joel -- Consider switching to defaultdict
        self.state_change_callbacks.get("error").append(callback)

    def on_error(callback):
        pass

    def on_messsage(callback):
        # Calls a function any time a message is received.
        pass

    def connection_state():
        pass

    def is_connected():
        return self.connection_state() == 'open'

    def remove(channel):
        """
        Removes a subscription from the socket.
        """
        pass

    def channel(topic, chan_params={}):
        chan = RealtimeSubscription(topic, chan_params, self)
        self.channels.push(chan)
        return chan

    def push(self, data):
        encoded_data = json.dumps(data)
        topic = data.get("topic")
        event = data.get("event")
        payload = data.get("payload")
        ref = data.get("ref")

        def callback(self):
            self.encode(data, lambda result: self.conn.send(result))

        print(f" Push {topic} {event} {ref}")
        self.send_buffer.push(callback)

    def on_conn_message(self, raw_message):
        # TODO : Joel -- implement decode
        self.decode(raw_message.data, lambda msg: extract_message(msg))

        def extract_message(msg):
            topic = msg.get("topic")
            event = msg.get("event")
            payload = msg.get("payload")
            ref = msg.get("ref")
            print(f"receive {payload} {topic} {event}")
        pass

    def endpoint_url(self):
        """
        Returns the URL of the websocket
        """
        pass

    def make_ref(self):
        """
        Return the next message ref, accounting for overflows
        """
        new_ref = self.ref + 1
        if new_ref == self.ref:
            self.ref = 0
        else:
            self.ref = new_ref

        return str(self.ref)

    def _on_conn_open(self):
        self.log('transport', f"connected to {self.endpoint_url()}")
        self._flush_send_buffer()
        # self.reconnect_timer.reset()
        # self._reset_heartbeat()
        map(self.state_change_callbacks.open)
        # .forEach((callback) => callback())!

    def _on_conn_close():
        pass

    def _on_conn_error():
        pass

    def _trigger_chan_error():
        pass

    def _append_params():
        pass

    def _flush_send_buffer():
        pass

    def _reset_heartbeat():
        pass

    def _send_heartbeat():
        pass
