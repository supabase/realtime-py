import asyncio
import os

from realtime.connection import Socket


def presence_callback(payload):
    print("presence: ", payload)


def postgres_changes_callback(payload):
    print("*: ", payload)


def postgres_changes_insert_callback(payload):
    print("INSERT: ", payload)


def postgres_changes_delete_callback(payload):
    print("DELETE: ", payload)


def postgres_changes_update_callback(payload):
    print("UPDATE: ", payload)


async def realtime(payload):
    print("async realtime ", payload)


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


async def test_postgres_changes(socket: Socket):
    await socket.connect()

    channel = socket.channel("test-postgres-changes")

    await channel.on_postgres_changes(
        "*", table="todos", callback=postgres_changes_callback
    ).on_postgres_changes(
        "INSERT", table="todos", callback=postgres_changes_insert_callback
    ).on_postgres_changes(
        "DELETE", table="todos", callback=postgres_changes_delete_callback
    ).on_postgres_changes(
        "UPDATE", table="todos", callback=postgres_changes_update_callback
    ).subscribe()

    await socket.listen()


async def main():
    URL = os.getenv("SUPABASE_URL")
    JWT = os.getenv("SUPABASE_ANON_KEY")

    # Setup the broadcast socket and channel
    socket = Socket(f"{URL}/realtime/v1", JWT, auto_reconnect=True)

    await test_broadcast_events(socket)
    # await test_postgres_changes(socket)


asyncio.run(main())
