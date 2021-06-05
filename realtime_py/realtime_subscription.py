from realtime_py.constants import CHANNEL_EVENT_JOIN
from realtime_py.push import Push


class RealtimeSubscription:
    def __init__(self, topic: str, params: dict, socket):
        timeout = 5
        socket.connect()
        channel = socket.set_channel("realtime:public:todos")
        self.join_push = Push(self, CHANNEL_EVENT_JOIN, params, timeout)
        pass

    def rejoin_until_connected():
        pass

    def subscribe():
        pass

    def on_close():
        pass

    def on_error():
        pass

    def on(event, callback):
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

    def is_errored():
        pass

    def is_joined():
        pass

    def is_joining():
        pass

    def is_leaving():
        pass
