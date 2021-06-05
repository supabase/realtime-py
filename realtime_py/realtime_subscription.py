from realtime_py.constants import CHANNEL_EVENT_JOIN, CHANNEL_EVENT_LEAVE, CHANNEL_STATE_CLOSED, CHANNEL_STATE_ERRORED, CHANNEL_STATE_JOINED, CHANNEL_STATE_LEAVING
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
            print(res)
            # self.state = CHANNEL_STATE_JOINED
            # for event in self.push_buffer:
            #     event.send()
            # self.push_buffer = []
            return "something"

        def post_reply_callback():
            pass
        self.join_push.receive('ok', post_ok_callback)
        channel.join().on('*', post_ok_callback)
        socket.listen()

    def rejoin_until_connected():
        pass

    def subscribe(self):
        pass

    def on_close():
        pass

    def on_error():
        pass

    def on(self, event, callback):
        pass

    def off(event):
        pass

    def can_push():
        pass

    def push(self, event, payload, timeout):
        push_event = Push(event, payload, timeout)
        if self.can_push():
            push_event.send()
        return push_event

    def unsubscribe(timeout):
        pass

    def on_message(event, payload, ref=""):
        """
        Overrideable message hook

        Receives all events for specialized message handling before dispatching to channel callbacks
        Must return the payload modified or unmodified
        """
        pass

    def is_member(self, is_topic):
        pass

    def join_ref(self):
        return self.join_push.ref

    def send_join(timeout):
        pass

    def rejoin(timeout):
        pass

    def trigger(event, payload, ref):
        pass

    def reply_event_name(self, ref):
        return f"chan_reply_{ref}"

    def is_closed():
        pass

    def is_errored(self):
        return self.state == CHANNEL_STATE_ERRORED

    def is_joined(self):
        return self.state == CHANNEL_STATE_JOINED

    def is_joining(self):
        pass

    def is_leaving(self):
        return self.state == CHANNEL_STATE_LEAVING
