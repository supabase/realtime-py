import os

from realtime.connection import Socket


def broadcast_callback(payload):
    print("broadcast: ", payload)


def presence_callback(payload):
    print("presence: ", payload)


def postgres_changes_callback(payload):
    print("postgres_changes: ", payload)


async def realtime(payload):
    print("async realtime ", payload)


URL = os.getenv("SUPABASE_URL")
JWT = os.getenv("SUPABASE_ANON_KEY")

# Setup the broadcast socket and channel
socket = Socket(URL, JWT, auto_reconnect=True)
socket.connect()

channel = socket.set_channel("test-topic", channel_params={"broadcast": {"self": True}})
channel.on_broadcast("test", callback=broadcast_callback).subscribe()

channel.send_broadcast("test", {"message": "Hello"})

socket.listen()
