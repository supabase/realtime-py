import asyncio
import os

import pytest
from dotenv import load_dotenv

from realtime.connection import Socket

load_dotenv()


@pytest.fixture
def socket() -> Socket:
    url = f"{os.getenv("SUPABASE_URL")}/realtime/v1"
    key = os.getenv("SUPABASE_ANON_KEY")
    return Socket(url, key)


@pytest.mark.asyncio
async def test_set_auth(socket: Socket):
    await socket.connect()

    await socket.set_auth("jwt")
    assert socket.access_token == "jwt"

    await socket.close()


@pytest.mark.asyncio
async def test_broadcast_events(socket: Socket):
    await socket.connect()
    asyncio.create_task(socket.listen())

    channel = socket.channel(
        "test-broadcast", params={"config": {"broadcast": {"self": True}}}
    )
    received_events = []

    def broadcast_callback(payload, **kwargs):
        print("broadcast: ", payload)
        received_events.append(payload)

    await channel.on_broadcast("test-event", callback=broadcast_callback).subscribe()

    await asyncio.sleep(1)

    # Send 3 broadcast events
    for i in range(3):
        await channel.send_broadcast("test-event", {"message": f"Event {i+1}"})

    # Wait a short time to ensure all events are processed
    await asyncio.sleep(1)

    assert len(received_events) == 3
    assert received_events[0]["payload"]["message"] == "Event 1"
    assert received_events[1]["payload"]["message"] == "Event 2"
    assert received_events[2]["payload"]["message"] == "Event 3"

    await socket.close()
