import RealtimeSubscription


class Push:
    def __init__(self, channel, event, payload, timeout):
        self.channel = channel
        self.event = event
        self.payload = payload
        self.timeout = timeout
        pass

    def send(self):
        self.channel.socket.push({
            topic: self.channel.topic,
            event: self.event,
            payload: self.payload,
            ref: self.ref

        })

    def receive(self, status, callback):
        self.channel.listeners.append([status, callback])
        return self

    def start_timeout():
        pass

    def trigger(self, status, response):
        pass
    
    def _cancel_ref_event(self):
        if not self.ref_event:
            return
        self.channel.off(self.ref_event)

    def _cancel_timeout():
        pass

    def _match_receive():
        pass
    
    def _has_received():
        pass

