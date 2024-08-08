import pytest
from unittest.mock import Mock, AsyncMock
from realtime.channel import RealtimeChannel, Push
from realtime.types import ChannelState
from realtime.message import ChannelEvents

@pytest.fixture
def mock_socket():
    return Mock(
        is_connected=Mock(return_value=True),
        access_token="test_token",
        api_key="test_api_key",
        endpoint="https://example.com",
    )

@pytest.fixture
@pytest.mark.asyncio
async def channel(mock_socket):
    return await RealtimeChannel(mock_socket, "test_topic", {"config": {}})

def test_channel_initialization(channel):
    assert channel.topic == "test_topic"
    assert channel.sub_topic == "test_topic"
    assert channel.state == ChannelState.CLOSED
    assert channel.joined_once == False
    assert isinstance(channel.join_push, Push)

@pytest.mark.asyncio
async def test_subscribe(channel):
    channel.socket.connect = AsyncMock()
    channel._rejoin = Mock()
    callback = Mock()
    result = await channel.subscribe(callback)

    assert result == channel
    assert channel.joined_once == True
    channel._rejoin.assert_called_once()
    channel.join_push.receive.assert_called()

@pytest.mark.asyncio
async def test_unsubscribe(channel):
    channel.state = ChannelState.JOINED
    channel.rejoin_timer = Mock(reset=Mock())
    channel.join_push = Mock(destroy=Mock())
    channel._trigger = Mock()

    result = await channel.unsubscribe()

    assert result == "ok"
    assert channel.state == ChannelState.LEAVING
    channel.rejoin_timer.reset.assert_called_once()
    channel.join_push.destroy.assert_called_once()

def test_on(channel):
    callback = Mock()
    result = channel.on("test_event", {"filter": "test"}, callback)

    assert result == channel
    assert "test_event" in channel.bindings
    assert len(channel.bindings["test_event"]) == 1
    assert channel.bindings["test_event"][0]["callback"] == callback

def test_off(channel):
    channel.bindings["test_event"] = [
        {"filter": "test1", "callback": Mock()},
        {"filter": "test2", "callback": Mock()},
    ]

    result = channel._off("test_event", {"filter": "test1"})

    assert result == channel
    assert len(channel.bindings["test_event"]) == 1
    assert channel.bindings["test_event"][0]["filter"] == "test2"

@pytest.mark.asyncio
async def test_push(channel):
    channel.joined_once = True
    channel._can_push = Mock(return_value=True)
    channel.socket.push = AsyncMock()

    push = await channel._push("test_event", {"payload": "test"})

    assert isinstance(push, Push)
    assert push.event == "test_event"
    assert push.payload == {"payload": "test"}
    channel.socket.push.assert_called_once()

def test_can_push(channel):
    channel.socket.is_connected = Mock(return_value=True)
    channel.state = ChannelState.JOINED

    assert channel._can_push() == True

    channel.state = ChannelState.JOINING
    assert channel._can_push() == False

def test_is_member(channel):
    channel.bindings["test_event"] = [
        {"filter": "test1", "callback": Mock()},
        {"filter": "test2", "callback": Mock()},
    ]

    assert channel._is_member("test_event", "test1") == True
    assert channel._is_member("test_event", "test3") == False
    assert channel._is_member("non_existent_event", "test1") == False

def test_on_close(channel):
    callback = Mock()
    channel.on_close(callback)

    assert ChannelState.CLOSED in channel.bindings
    assert len(channel.bindings[ChannelState.CLOSED]) == 1
    assert channel.bindings[ChannelState.CLOSED][0]["callback"] == callback

def test_on_error(channel):
    callback = Mock()
    channel.on_error(callback)

    assert ChannelState.ERRORED in channel.bindings
    assert len(channel.bindings[ChannelState.ERRORED]) == 1
    assert isinstance(channel.bindings[ChannelState.ERRORED][0]["callback"], type(lambda: None))

@pytest.mark.asyncio
async def test_send_broadcast(channel):
    channel._can_push = Mock(return_value=False)
    channel._fetch_with_timeout = AsyncMock(return_value=Mock(status=200))

    result = await channel.send(
        {"type": "broadcast", "event": "test_event", "payload": {"message": "test"}}
    )

    assert result == "ok"
    channel._fetch_with_timeout.assert_called_once()

def test_update_join_payload(channel):
    channel.join_push = Mock(update_payload=Mock())
    new_payload = {"new_key": "new_value"}

    channel.update_join_payload(new_payload)

    channel.join_push.update_payload.assert_called_once_with(new_payload)