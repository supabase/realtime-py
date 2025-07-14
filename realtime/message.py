from typing import Any, List, Literal, Mapping, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter
from typing_extensions import TypeAlias

from .types import (
    ChannelEvents,
    RawPresenceDiff,
    RealtimeChannelOptions,
    RealtimePostgresChangesListenEvent,
)


class Message(BaseModel):
    """
    Dataclass abstraction for message
    """

    event: str
    payload: Mapping[str, Any]
    topic: str
    ref: Optional[str] = None
    join_ref: Optional[str] = None


class ConnectionMessage(BaseModel):
    event: Literal[ChannelEvents.join]
    topic: str
    ref: str
    payload: RealtimeChannelOptions


class PostgresRowChange(BaseModel):
    id: int
    event: RealtimePostgresChangesListenEvent
    table: str
    schema_: Optional[str] = Field(alias="schema", default=None)
    filter: Optional[str] = None


class ConnectionReplyPostgresChanges(BaseModel):
    postgres_changes: Optional[List[PostgresRowChange]] = None


class ConnectionReplyPayload(BaseModel):
    response: ConnectionReplyPostgresChanges
    status: Literal["ok", "error"]


class ConnectionReplyMessage(BaseModel):
    event: Literal[ChannelEvents.reply]
    topic: str
    payload: ConnectionReplyPayload
    ref: Optional[str] = None


class SystemPayload(BaseModel):
    channel: str
    extension: Literal["postgres_changes"]
    message: Literal["Subscribed to PostgreSQL", "Subscribing to PostgreSQL failed"]
    status: Literal["ok", "error"]


class SystemMessage(BaseModel):
    event: Literal[ChannelEvents.system]
    topic: str
    payload: SystemPayload
    ref: Literal[None]


class HeartbeatPayload(BaseModel):
    pass


class HeartbeatMessage(BaseModel):
    event: Literal[ChannelEvents.heartbeat]
    topic: Literal["phoenix"]
    ref: str
    payload: HeartbeatPayload


class AccessTokenPayload(BaseModel):
    access_token: str


class AccessTokenMessage(BaseModel):
    event: Literal[ChannelEvents.access_token]
    topic: str
    payload: AccessTokenPayload


class PostgresChangesColumn(BaseModel):
    name: str
    type: str


class PostgresChangesData(BaseModel):
    schema_: str = Field(alias="schema")
    table: str
    commit_timestamp: str
    type: RealtimePostgresChangesListenEvent
    errors: Optional[str]
    columns: List[PostgresChangesColumn]
    record: Optional[dict[str, Any]] = None
    old_record: Optional[dict[str, Any]] = None  # todo: improve this


class PostgresChangesPayload(BaseModel):
    data: PostgresChangesData
    ids: List[int]


class PostgresChangesMessage(BaseModel):
    event: Literal[ChannelEvents.postgres_changes]
    topic: str
    payload: PostgresChangesPayload
    ref: Literal[None]


class BroadcastMessage(BaseModel):
    event: Literal[ChannelEvents.broadcast]
    topic: str
    payload: dict[str, Any]
    ref: Literal[None]


class PresenceMessage(BaseModel):
    event: Literal[ChannelEvents.presence]
    topic: str
    payload: dict[str, Any]
    ref: Literal[None]


class PresenceStateMessage(BaseModel):
    event: Literal[ChannelEvents.presence_state]
    topic: str
    payload: dict[str, Any]
    ref: Literal[None]


class PresenceDiffMessage(BaseModel):
    event: Literal[ChannelEvents.presence_diff]
    topic: str
    payload: RawPresenceDiff
    ref: Literal[None]


ServerMessage: TypeAlias = Union[
    SystemMessage,
    ConnectionReplyMessage,
    HeartbeatMessage,
    BroadcastMessage,
    PresenceStateMessage,
    PresenceDiffMessage,
    PostgresChangesMessage,
]
ServerMessageAdapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)
ClientMessage: TypeAlias = Union[
    ConnectionMessage, HeartbeatMessage, BroadcastMessage, PresenceMessage
]
