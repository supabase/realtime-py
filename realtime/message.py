from typing import Any, Mapping, Optional

from pydantic import BaseModel


class Message(BaseModel):
    """
    Dataclass abstraction for message
    """

    event: str
    payload: Mapping[str, Any]
    ref: Any
    topic: str
    join_ref: Optional[str] = None
