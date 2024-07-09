from realtime.connection import Socket
from realtime.channel import CallbackListener, Channel
import os
import time
def broadcast_callback(payload):
    print("broadcast: ", payload)


def presence_callback(payload):
    print("presence: ", payload)


def postgres_changes_callback(payload):
    print("postgres_changes: ", payload)


async def realtime(payload):
    print("async realtime ", payload)

if __name__ == "__main__":
    ID = 'unjmcdnawyleplexbxja'#os.getenv("SUPABASE_ID")
    URL = f"https://{ID}.supabase.co"
    JWT = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVuam1jZG5hd3lsZXBsZXhieGphIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTcxOTkzNDY2NCwiZXhwIjoyMDM1NTEwNjY0fQ.qL9CBx9wUEdUWTRjxJTEIhUhnHDeeexu3UHiLqxqQ7o'#os.getenv("API_KEY")

    # Setup the broadcast socket and channel
    broad_socket = Socket(URL, JWT, auto_reconnect=True)
    broadcast_channel = Channel(broad_socket, topic="broadcast-test")
    broadcast_channel.on_broadcast("test", callback=broadcast_callback).subscribe()
    time.sleep(6)

    # Setup another socket for changes
    s = Socket(URL, JWT, auto_reconnect=True)
    channel = Channel(s, topic="changes-test")
    channel.on_postgres_changes(table="realtime_test", schema="public", event="*", callback=postgres_changes_callback).eq("id", 10).subscribe()

    # Setup the socket for set_channel
    ss = Socket(URL, JWT, auto_reconnect=True)
    ss.connect()

    # Provide the required channel_params argument
    socket_channel = ss.set_channel(channel.topic, channel_params={})
    socket_channel.on_broadcast("test", broadcast_callback).subscribe()
    socket_channel.send_broadcast("test", {"message": "Hello from the other side"})
    time.sleep(6)
