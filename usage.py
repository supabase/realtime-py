import asyncio
from typing import Optional

from realtime.channel import RealtimeSubscribeStates
from realtime.client import RealtimeClient


async def main():
    REALTIME_URL = "ws://localhost:4000/websocket"
    API_KEY = "1234567890"

    socket = RealtimeClient(REALTIME_URL, API_KEY)
    channel = socket.channel("test-channel")

    def _on_subscribe(status: RealtimeSubscribeStates, err: Optional[Exception]):
        if status == RealtimeSubscribeStates.SUBSCRIBED:
            print("Connected!")
        elif status == RealtimeSubscribeStates.CHANNEL_ERROR:
            print(f"There was an error subscribing to channel: {err.args}")
        elif status == RealtimeSubscribeStates.TIMED_OUT:
            print("Realtime server did not respond in time.")
        elif status == RealtimeSubscribeStates.CLOSED:
            print("Realtime channel was unexpectedly closed.")

    await channel.subscribe(_on_subscribe)


async def test(socket: RealtimeClient):
    channel = socket.channel("db-changes")

    channel.on_postgres_changes(
        "*",
        schema="public",
        callback=lambda payload: print("All changes in public schema: ", payload),
    )

    channel.on_postgres_changes(
        "INSERT",
        schema="public",
        table="messages",
        callback=lambda payload: print("All inserts in messages table: ", payload),
    )

    channel.on_postgres_changes(
        "UPDATE",
        schema="public",
        table="users",
        filter="username=eq.Realtime",
        callback=lambda payload: print(
            "All updates on users table when username is Realtime: ", payload
        ),
    )

    channel.subscribe(
        lambda status, err: status == RealtimeSubscribeStates.SUBSCRIBED
        and print("Ready to receive database changes!")
    )


if __name__ == "__main__":
    asyncio.run(main())
