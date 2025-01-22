import asyncio
import datetime
import logging
import os
from typing import Optional

import requests

from realtime import AsyncRealtimeChannel, AsyncRealtimeClient, RealtimeSubscribeStates

logging.basicConfig(
    format="%(asctime)s:%(levelname)s - %(message)s", level=logging.INFO
)
URL = os.getenv("SUPABASE_URL") or "http://127.0.0.1:54321"
JWT = (
    os.getenv("SUPABASE_ANON_KEY")
    or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
)


def presence_callback(payload):
    print("presence: ", payload)


def postgres_changes_callback(payload, *args):
    print("*: ", payload)


def postgres_changes_insert_callback(payload, *args):
    print("INSERT: ", payload)


def postgres_changes_delete_callback(payload, *args):
    print("DELETE: ", payload)


def postgres_changes_update_callback(payload, *args):
    print("UPDATE: ", payload)


async def realtime(payload):
    print("async realtime ", payload)


async def test_broadcast_events(socket: AsyncRealtimeClient):
    await socket.connect()

    channel: AsyncRealtimeChannel = socket.channel(
        "test-broadcast", params={"config": {"broadcast": {"self": True}}}
    )
    received_events = []

    def broadcast_callback(payload, *args):
        print("broadcast: ", payload)
        received_events.append(payload)

    await channel.on_broadcast("test-event", callback=broadcast_callback).subscribe()

    asyncio.create_task(socket.listen())

    await asyncio.sleep(1)

    # Send 3 broadcast events
    for i in range(3):
        await channel.send_broadcast("test-event", {"message": f"Event {i+1}"})

    # Wait a short time to ensure all events are processed
    await asyncio.sleep(1)

    print(received_events)

    assert len(received_events) == 3
    assert received_events[0]["payload"]["message"] == "Event 1"
    assert received_events[1]["payload"]["message"] == "Event 2"
    assert received_events[2]["payload"]["message"] == "Event 3"


async def test_postgres_changes(socket: AsyncRealtimeClient):
    await socket.connect()

    # Add your access token here
    # await socket.set_auth("ACCESS_TOKEN")

    channel: AsyncRealtimeChannel = socket.channel("test-postgres-changes")

    def on_subscribe(status: RealtimeSubscribeStates, err: Optional[Exception]) -> None:
        subscribed = True
        print(f"ON_SUBSCRIBE: {status} (Error: {err})")

    await channel.on_postgres_changes(
        "*", table="todos", callback=postgres_changes_callback
    ).on_postgres_changes(
        "INSERT",
        table="todos",
        filter="description=eq.test",
        callback=postgres_changes_insert_callback,
    ).on_postgres_changes(
        "DELETE",
        table="todos",
        callback=postgres_changes_delete_callback,
    ).on_postgres_changes(
        "UPDATE",
        table="todos",
        callback=postgres_changes_update_callback,
    ).subscribe(
        on_subscribe
    )

    asyncio.create_task(socket.listen())

    # Wait a short time to ensure we are properly listening
    await asyncio.sleep(1)

    headers = {"Prefer": "return=representation"}

    # does not match filter and will therefore only be received by the * listen, but not the INSERT listen
    requests.post(
        f"{URL}/rest/v1/todos",
        headers=headers,
        json={"description": "does not match insert filter"},
    )
    await asyncio.sleep(1)

    res = requests.post(
        f"{URL}/rest/v1/todos", headers=headers, json={"description": "test"}
    )
    element = res.json()[0]
    todo_id = element["id"]
    assert element["description"] == "test"
    await asyncio.sleep(1)

    requests.patch(
        f"{URL}/rest/v1/todos?id=eq.{todo_id}",
        headers=headers,
        json={"description": "updated test"},
    )

    requests.delete(f"{URL}/rest/v1/todos?id=eq.{todo_id}", headers=headers)

    # final wait is needed to properly listen
    await asyncio.sleep(1)


async def test_presence(socket: AsyncRealtimeClient):
    await socket.connect()

    asyncio.create_task(socket.listen())

    channel: AsyncRealtimeChannel = socket.channel("room")

    def on_sync():
        print("on_sync", channel.presence.state)

    def on_join(key, current_presences, new_presences):
        print("on_join", key, current_presences, new_presences)

    def on_leave(key, current_presences, left_presences):
        print("on_leave", key, current_presences, left_presences)

    await channel.on_presence_sync(on_sync).on_presence_join(on_join).on_presence_leave(
        on_leave
    ).subscribe()

    await channel.track(
        {"user_id": "1", "online_at": datetime.datetime.now().isoformat()}
    )
    await asyncio.sleep(1)

    await channel.track(
        {"user_id": "2", "online_at": datetime.datetime.now().isoformat()}
    )
    await asyncio.sleep(1)

    await channel.untrack()
    await asyncio.sleep(1)


async def main():
    # Setup the broadcast socket and channel
    socket = AsyncRealtimeClient(f"{URL}/realtime/v1", JWT, auto_reconnect=True)

    await test_broadcast_events(socket)
    await test_postgres_changes(socket)
    await test_presence(socket)


asyncio.run(main())
