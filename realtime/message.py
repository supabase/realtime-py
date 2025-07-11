from typing import Any, List, Literal, Mapping, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter
from typing_extensions import TypeAlias

from .types import (
    ChannelEvents,
    PresenceDiff,
    RealtimeChannelOptions,
    RealtimePostgresChangesListenEvent,
)


class ConnectionMessage(BaseModel):
    event: Literal[ChannelEvents.join]
    topic: str
    ref: str
    payload: RealtimeChannelOptions


class PostgresRowChange(BaseModel):
    id: int
    event: RealtimePostgresChangesListenEvent
    _schema: str = Field(alias="schema")
    table: str
    filter: str


class ConnectionReplyPostgresChanges(BaseModel):
    postgres_changes: List[PostgresRowChange]


class ConnectionReplyPayload(BaseModel):
    response: ConnectionReplyPostgresChanges
    status: Literal["ok", "error"]


class ConnectionReplyMessage(BaseModel):
    event: Literal[ChannelEvents.reply]
    topic: str
    payload: ConnectionReplyPayload
    ref: str


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


class PostgresChangesData(BaseModel):
    _schema: str = Field(alias="schema")
    table: str
    commit_timestamp: str
    eventType: RealtimePostgresChangesListenEvent
    errors: Optional[str]
    new: dict[str, Union[bool, int, str, None]]
    old: dict[str, Union[int, str]]


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
    payload: PresenceDiff
    ref: Literal[None]


ServerMessage: TypeAlias = Union[
    ConnectionReplyMessage,
    HeartbeatMessage,
    BroadcastMessage,
    PresenceStateMessage,
    PresenceDiffMessage,
]
ServerMessageAdapter = TypeAdapter(ServerMessage)
ClientMessage: TypeAlias = Union[
    ConnectionMessage, HeartbeatMessage, BroadcastMessage, PresenceMessage
]
