from realtime_py.constants import CHANNEL_EVENT_JOIN, CHANNEL_STATE_CLOSED, CHANNEL_STATE_ERRORED, CHANNEL_STATE_JOINED, CHANNEL_STATE_JOINING, CHANNEL_STATE_LEAVING
from realtime_py.push import Push
from realtime_py.transformers import convert_change_data


class RealtimeSubscription:
    def __init__(self, topic: str, params: dict, socket: any):
        timeout = 5
        socket.connect()
        channel = socket.set_channel(topic)
        self.state = CHANNEL_STATE_CLOSED

        self.join_push = Push(channel, CHANNEL_EVENT_JOIN, params, timeout)

        def post_ok_callback(payload):
            print(payload)
            columns = payload.get("columns")
            records = payload.get("record")
            res = convert_change_data(columns, records)
            return "something"

        self.join_push.receive('ok', post_ok_callback)
        channel.join().on('*', post_ok_callback)
        socket.listen()

    def push(self, event, payload, timeout):
        push_event = Push(event, payload, timeout)
        if self.can_push():
            push_event.send()
        return push_event

    def is_closed(self):
        return self.state == CHANNEL_STATE_CLOSED

    def is_errored(self):
        return self.state == CHANNEL_STATE_ERRORED

    def is_joined(self):
        return self.state == CHANNEL_STATE_JOINED

    def is_joining(self):
        return self.state == CHANNEL_STATE_JOINING

    def is_leaving(self):
        return self.state == CHANNEL_STATE_LEAVING
