import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dotenv import load_dotenv

from realtime.connection import Serializer, Socket, Timer
from realtime.types import ConnectionState

load_dotenv()


@pytest.fixture
def socket() -> Socket:
    return Socket("wss://example.com")


def test_socket_initialization(socket: Socket):
    assert socket.endpoint == "wss://example.com/websocket"
    assert socket.http_endpoint == "https://example.com"
    assert socket.timeout == 10000
    assert socket.heartbeat_interval_ms == 30000
    assert socket.channels == []
    assert socket.conn is None


@pytest.mark.asyncio
async def test_connect(socket: Socket):
    with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn

        await socket.connect()

        mock_connect.assert_called_once_with(socket._endpoint_url())
        assert socket.conn == mock_conn


@pytest.mark.asyncio
async def test_disconnect(socket: Socket):
    mock_conn = AsyncMock()
    socket.conn = mock_conn
    socket.reconnect_timer = AsyncMock()

    await socket.disconnect()

    mock_conn.close.assert_awaited_once()
    assert socket.conn is None
    socket.reconnect_timer.reset.assert_called_once()


def test_connection_state(socket: Socket):
    assert socket.connection_state() == ConnectionState.CLOSED

    socket.conn = AsyncMock()
    socket.conn.state = 1  # OPEN
    assert socket.connection_state() == ConnectionState.OPEN


def test_is_connected(socket: Socket):
    assert not socket.is_connected()

    socket.conn = AsyncMock()
    socket.conn.state = 1  # OPEN
    assert socket.is_connected()


@pytest.mark.asyncio
async def test_channel(socket: Socket):
    channel = socket.channel("room:123")
    assert channel.topic == "realtime:room:123"
    assert channel.sub_topic == "room:123"
    assert channel in socket.channels


def test_set_auth(socket: Socket):
    channel1 = MagicMock()
    channel2 = MagicMock()
    socket.channels = [channel1, channel2]

    socket.set_auth("new_token")

    assert socket.access_token == "new_token"
    channel1.update_join_payload.assert_called_with({"access_token": "new_token"})
    channel2.update_join_payload.assert_called_with({"access_token": "new_token"})


def test_serializer():
    serializer = Serializer()
    data = {"key": "value"}
    encoded = serializer.encode(data)
    decoded = serializer.decode(encoded)
    assert decoded == data


@pytest.mark.asyncio
async def test_timer():
    mock_callback = AsyncMock()
    timer = Timer(mock_callback, 1)

    timer.reset()
    await asyncio.sleep(1.1)

    mock_callback.assert_called_once()
