from .connection import Socket
from .channel import Channel
from typing import Any, Dict, DefaultDict, List


class RealTimeClient:

    def __init__(self, url, token):
        self.socket = Socket(url, token)

    def connect(self) -> None:
        self.socket.connect()

    def close(self) -> None:
        self.socket.close()

    def listen(self) -> None:
        self.socket.listen()

    def set_channel(self, topic: str, channel_params: Dict[str, Any]) -> Channel:
        return self.socket.set_channel(topic, channel_params)

    def get_channels(self) -> Dict[str, List[Channel]]:
        return self.socket.channels
