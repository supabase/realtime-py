from realtime_py.constants import DEFAULT_TIMEOUT


class Push:
    def __init__(self, channel, event: str, payload: dict, timeout: float = DEFAULT_TIMEOUT):
        self.channel = channel
        self.event = event
        self.payload = payload
        self.timeout = timeout

    def send(self):
        self.channel.socket.push({
            "topic": self.channel.topic,
            "event": self.event,
            "payload": self.payload,
            "ref": self.ref

        })
        print("sent")

    def receive(self, status, callback):
        self.channel.listeners.append([status, callback])
        return self

    def start_timeout(self):
        self.ref = self.channel.socket.make_ref()
        self.refEvent = self.channel.reply_event_name(self.ref)

    def trigger(self, status, response):
        pass

    def _cancel_ref_event(self):
        if not self.ref_event:
            return
        self.channel.off(self.ref_event)

    # def _cancel_timeout():
    #     pass

    # def _match_receive():
    #     pass

    # def _has_received():
    #     pass
