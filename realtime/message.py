from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class Message:
    """
    Represents a message exchanged over the WebSocket.
    """

    topic: str
    event: str
    payload: Dict[str, Any]
    ref: Optional[str] = None
    join_ref: Optional[str] = None
