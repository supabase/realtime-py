import os
import asyncio
import re
from realtime.channel import RealtimeChannel

from realtime.connection import Socket, RealtimeClientOptions


def broadcast_callback(payload):
    print("broadcast: ", payload)


def presence_callback(payload):
    print("presence: ", payload)


def postgres_changes_callback(payload):
    print("postgres_changes: ", payload)


async def realtime(payload):
    print("async realtime ", payload)

async def main():
    URL = os.getenv("SUPABASE_URL")
    JWT = os.getenv("SUPABASE_ANON_KEY")

    URL = re.sub(r'^http', 'ws', f"{URL}/realtime/v1")
    socket = Socket(URL, options=RealtimeClientOptions(params={"apikey": JWT}))
    
    channel: RealtimeChannel = socket.channel("test-topic", {"broadcast": {"self": True}})

    await channel.on('broadcast', {"event": "test"}, callback=broadcast_callback).subscribe()

    await channel.send({"type": "broadcast", "event": "test", "payload": "hello"})

    await asyncio.sleep(2)

    # await socket.disconnect()

asyncio.run(main())
