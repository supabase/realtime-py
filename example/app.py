import os

from realtime.channel import Channel
from realtime.connection import Socket


def broadcast_callback(payload):
    print("broadcast: ", payload)


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


URL = os.getenv("SUPABASE_URL")
JWT = os.getenv("SUPABASE_ANON_KEY")

# Setup the broadcast socket and channel
socket = Socket(URL, JWT, auto_reconnect=True)
socket.connect()

socket.set_auth(
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzIzMTQwMTU2LCJpYXQiOjE3MjMxMzY1NTYsImlzcyI6Imh0dHA6Ly8xMjcuMC4wLjE6NTQzMjEvYXV0aC92MSIsInN1YiI6ImYwNDBmNmY4LTA2YTUtNDA1My04YzQzLTcyMjBlZWMzZDMyZSIsImVtYWlsIjoidGVzdEBtYWlsLmNvbSIsInBob25lIjoiIiwiYXBwX21ldGFkYXRhIjp7InByb3ZpZGVyIjoiZW1haWwiLCJwcm92aWRlcnMiOlsiZW1haWwiXX0sInVzZXJfbWV0YWRhdGEiOnt9LCJyb2xlIjoiYXV0aGVudGljYXRlZCIsImFhbCI6ImFhbDEiLCJhbXIiOlt7Im1ldGhvZCI6InBhc3N3b3JkIiwidGltZXN0YW1wIjoxNzIzMTM2NTU2fV0sInNlc3Npb25faWQiOiIwMjFkNDg1MC1iNThlLTRiNTEtYTU0NC1hZTg0NzAzOTE2ZmEiLCJpc19hbm9ueW1vdXMiOmZhbHNlfQ.pDYM3iLTzkDcbHjz_UtAUqWj5YfUsVwHsXZC7OKE27I"
)

channel: Channel = socket.set_channel(
    "test-topic", channel_params={"broadcast": {"self": True}}
)
channel.on_broadcast("test", callback=broadcast_callback).on_postgres_changes(
    "*", table="todos", callback=postgres_changes_callback
).on_postgres_changes(
    "INSERT", table="todos", callback=postgres_changes_insert_callback
).on_postgres_changes(
    "DELETE", table="todos", callback=postgres_changes_delete_callback
).on_postgres_changes(
    "UPDATE", table="todos", callback=postgres_changes_update_callback
).subscribe()

channel.send_broadcast("test", {"message": "Hello"})

socket.listen()
