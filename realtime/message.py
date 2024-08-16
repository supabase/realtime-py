from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class Message:
    """
    Dataclass abstraction for message
    """

    event: str
    payload: Dict[str, Any]
    ref: Any
    topic: str
    join_ref: Optional[str] = None

    def __hash__(self):
        return hash(
            (
                self.event,
                tuple(list(self.payload.values())),
                self.ref,
                self.topic,
                self.join_ref,
            )
        )
