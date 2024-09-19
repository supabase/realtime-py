import asyncio
import datetime
import os
from typing import List, Tuple

import pytest
from dotenv import load_dotenv

from realtime import AsyncRealtimeChannel, AsyncRealtimeClient, AsyncRealtimePresence
from realtime.types import Presence

load_dotenv()

URL = os.getenv("SUPABASE_URL") or "http://127.0.0.1:54321"
ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ..."


@pytest.mark.asyncio
async def test_presence(socket: AsyncRealtimeClient):
    await socket.connect()

    channel: AsyncRealtimeChannel = socket.channel("room")

    join_events: List[Tuple[str, List[Presence], List[Presence]]] = []
    leave_events: List[Tuple[str, List[Presence], List[Presence]]] = []

    sync_event = asyncio.Event()

    async def on_sync():
        sync_event.set()

    async def on_join(
        key: str,
        current_presences: List[Presence],
        new_presences: List[Presence],
    ):
        join_events.append((key, current_presences, new_presences))

    async def on_leave(
        key: str,
        current_presences: List[Presence],
        left_presences: List[Presence],
    ):
        leave_events.append((key, current_presences, left_presences))

    channel.on_presence_sync(on_sync)
    channel.on_presence_join(on_join)
    channel.on_presence_leave(on_leave)
    await channel.subscribe()

    # Wait for the first sync event, which should be immediate
    await asyncio.wait_for(sync_event.wait(), 5)
    sync_event.clear()

    # Track first user
    user1 = {"user_id": "1", "online_at": datetime.datetime.now().isoformat()}
    await channel.track(user1)

    await asyncio.wait_for(sync_event.wait(), 5)
    sync_event.clear()

    # Assert first user is in the presence state
    presences = [(state, value) for state, value in channel.presence.state.items()]

    assert len(presences) == 1
    assert len(presences[0][1]) == 1
    assert presences[0][1][0].get("user_id") == user1["user_id"]
    assert presences[0][1][0].get("online_at") == user1["online_at"]
    assert "phx_ref" in presences[0][1][0]

    assert len(join_events) == 1
    assert len(join_events[0][2]) == 1
    assert join_events[0][2][0].metadata.get("user_id") == user1["user_id"]
    assert join_events[0][2][0].metadata.get("online_at") == user1["online_at"]
    assert "phx_ref" in join_events[0][2][0]

    # Track second user
    user2 = {"user_id": "2", "online_at": datetime.datetime.now().isoformat()}
    await channel.track(user2)

    await asyncio.wait_for(sync_event.wait(), 5)
    sync_event.clear()

    # Assert both users are in the presence state
    presences = channel.presence.state
    user_ids = []
    for key, value in presences.items():
        assert len(value) == 1
        user_ids.append(value[0].get("user_id"))
        assert "online_at" in value[0]
        assert "phx_ref" in value[0]
    assert "1" in user_ids
    assert "2" in user_ids

    assert len(join_events) == 2
    assert len(join_events[1][2]) == 1
    assert join_events[1][2][0].metadata.get("user_id") == user2["user_id"]
    assert join_events[1][2][0].metadata.get("online_at") == user2["online_at"]
    assert "phx_ref" in join_events[1][2][0]

    # Untrack users
    await channel.untrack()

    await asyncio.wait_for(sync_event.wait(), 5)

    # Assert presence state is empty and leave events were triggered
    assert channel.presence.state == {}
    assert len(leave_events) >= 2  # There might be additional leave events
    # Ensure that both users have left
    user_keys_left = [event[0] for event in leave_events]
    assert "1" in user_keys_left or "user1" in user_keys_left
    assert "2" in user_keys_left or "user2" in user_keys_left

    await socket.disconnect()


def test_transform_state_raw_presence_state():
    raw_state = {
        "user1": {
            "metas": [
                {"phx_ref": "ABC123", "user_id": "user1", "status": "online"},
                {
                    "phx_ref": "DEF456",
                    "phx_ref_prev": "ABC123",
                    "user_id": "user1",
                    "status": "away",
                },
            ]
        },
        "user2": {
            "metas": [{"phx_ref": "GHI789", "user_id": "user2", "status": "offline"}]
        },
    }

    expected_output = {
        "user1": [
            {"phx_ref": "ABC123", "user_id": "user1", "status": "online"},
            {"phx_ref": "DEF456", "user_id": "user1", "status": "away"},
        ],
        "user2": [{"phx_ref": "GHI789", "user_id": "user2", "status": "offline"}],
    }

    result = AsyncRealtimePresence._transform_state(raw_state)
    assert result == expected_output


def test_transform_state_already_transformed():
    transformed_state = {
        "user1": [{"phx_ref": "ABC123", "user_id": "user1", "status": "online"}],
        "user2": [{"phx_ref": "GHI789", "user_id": "user2", "status": "offline"}],
    }

    result = AsyncRealtimePresence._transform_state(transformed_state)
    assert result == transformed_state


def test_transform_state_mixed_input():
    mixed_state = {
        "user1": {
            "metas": [
                {"phx_ref": "ABC123", "user_id": "user1", "status": "online"},
                {
                    "phx_ref": "DEF456",
                    "phx_ref_prev": "ABC123",
                    "user_id": "user1",
                    "status": "away",
                },
            ]
        },
        "user2": [{"user_id": "user2", "status": "offline"}],
    }

    expected_output = {
        "user1": [
            {"phx_ref": "ABC123", "user_id": "user1", "status": "online"},
            {"phx_ref": "DEF456", "user_id": "user1", "status": "away"},
        ],
        "user2": [{"user_id": "user2", "status": "offline"}],
    }

    result = AsyncRealtimePresence._transform_state(mixed_state)
    assert result == expected_output


def test_transform_state_empty_input():
    empty_state = {}
    result = AsyncRealtimePresence._transform_state(empty_state)
    assert result == {}


def test_transform_state_additional_fields():
    state_with_additional_fields = {
        "user1": {
            "metas": [
                {
                    "phx_ref": "ABC123",
                    "user_id": "user1",
                    "status": "online",
                    "extra": "data",
                }
            ]
        }
    }

    expected_output = {
        "user1": [
            {
                "phx_ref": "ABC123",
                "user_id": "user1",
                "status": "online",
                "extra": "data",
            }
        ]
    }

    result = AsyncRealtimePresence._transform_state(state_with_additional_fields)
    assert result == expected_output
