import asyncio
import datetime
import logging
import os

from realtime import AsyncRealtimeChannel, AsyncRealtimeClient

# Configure logging
logging.basicConfig(
    format="%(asctime)s:%(levelname)s - %(message)s", level=logging.INFO
)


async def test_broadcast_events(socket: AsyncRealtimeClient):
    """
    Test broadcasting events over a channel and ensure they are received correctly.
    """
    # Create a channel with broadcast configuration
    channel = socket.channel("test-broadcast", params={"broadcast": {"self": True}})
    received_events = []

    # Define an async callback for broadcast events
    async def broadcast_callback(payload, ref):
        print("Received broadcast:", payload)
        received_events.append(payload)

    # Register the broadcast callback and subscribe to the channel
    channel.on_broadcast("test-event", callback=broadcast_callback)
    await channel.subscribe()

    # Allow some time for the subscription to complete
    await asyncio.sleep(1)

    # Send 3 broadcast events
    for i in range(3):
        await channel.send_broadcast("test-event", {"message": f"Event {i + 1}"})

    # Wait a short time to ensure all events are processed
    await asyncio.sleep(1)

    # Verify that all events have been received
    assert len(received_events) == 3
    assert received_events[0]["message"] == "Event 1"
    assert received_events[1]["message"] == "Event 2"
    assert received_events[2]["message"] == "Event 3"


async def test_postgres_changes(socket: AsyncRealtimeClient):
    """
    Test listening to Postgres changes on a table and handle different event types.
    """
    # Create a channel for Postgres changes
    channel = socket.channel("test-postgres-changes")

    # Define async callbacks for different Postgres change events
    async def postgres_changes_callback(payload, ref):
        print("Received Postgres change (*):", payload)

    async def postgres_changes_insert_callback(payload, ref):
        print("Received Postgres INSERT:", payload)

    async def postgres_changes_delete_callback(payload, ref):
        print("Received Postgres DELETE:", payload)

    async def postgres_changes_update_callback(payload, ref):
        print("Received Postgres UPDATE:", payload)

    # Register the callbacks for different events and subscribe to the channel
    await channel.on_postgres_changes(
        "*", table="todos", callback=postgres_changes_callback
    ).on_postgres_changes(
        "INSERT",
        table="todos",
        filter="id=eq.10",
        callback=postgres_changes_insert_callback,
    ).on_postgres_changes(
        "DELETE", table="todos", callback=postgres_changes_delete_callback
    ).on_postgres_changes(
        "UPDATE", table="todos", callback=postgres_changes_update_callback
    ).subscribe()

    # Keep the test running to receive events (adjust the sleep time as needed)
    await asyncio.sleep(10)


async def test_presence(socket: AsyncRealtimeClient):
    """
    Test presence functionality by tracking and untracking users and handling presence events.
    """
    # Create a channel for presence tracking
    channel: AsyncRealtimeChannel = socket.channel("room")

    # Define async callbacks for presence events
    async def on_sync():
        print("Presence sync:", channel.presence.state)

    async def on_join(key, current_presences, new_presences):
        print(
            f"User '{key}' joined. Current: {current_presences}, New: {new_presences}"
        )

    async def on_leave(key, current_presences, left_presences):
        print(
            f"User '{key}' left. Current: {current_presences}, Left: {left_presences}"
        )

    # Register the presence callbacks and subscribe to the channel
    await channel.on_presence_sync(on_sync).on_presence_join(on_join).on_presence_leave(
        on_leave
    ).subscribe()

    # Track presence for user 1
    await channel.track(
        {"user_id": "1", "online_at": datetime.datetime.now().isoformat()}
    )
    await asyncio.sleep(1)

    # Track presence for user 2
    await channel.track(
        {"user_id": "2", "online_at": datetime.datetime.now().isoformat()}
    )
    await asyncio.sleep(1)

    # Untrack presence
    await channel.untrack()
    await asyncio.sleep(1)


async def main():
    # Get the URL and JWT from environment variables or use defaults
    URL = os.getenv("SUPABASE_URL") or "http://127.0.0.1:54321"
    JWT = (
        os.getenv("SUPABASE_ANON_KEY")
        or "your-jwt-token-here"  # Replace with your actual JWT token
    )

    # Initialize the AsyncRealtimeClient
    socket = AsyncRealtimeClient(f"{URL}/realtime/v1", JWT, auto_reconnect=True)
    await socket.connect()

    # Run the test functions
    await test_broadcast_events(socket)
    await test_postgres_changes(socket)
    await test_presence(socket)

    # Keep the main function running to receive events (adjust the sleep time as needed)
    await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
