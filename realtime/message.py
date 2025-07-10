from typing import Any, Mapping, Optional

from pydantic import BaseModel


class Message(BaseModel):
    """
    Dataclass abstraction for message
    """

    event: str
    payload: Mapping[str, Any]
    topic: str
    ref: Optional[str] = None
    join_ref: Optional[str] = None
