import asyncio
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


async def main():
    URL = os.getenv("SUPABASE_URL")
    JWT = os.getenv("SUPABASE_ANON_KEY")

    # Setup the broadcast socket and channel
    socket = Socket(URL, JWT, auto_reconnect=True)
    await socket.connect()

    await socket.set_auth(
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzIzMTQ2Njc0LCJpYXQiOjE3MjMxNDMwNzQsImlzcyI6Imh0dHA6Ly8xMjcuMC4wLjE6NTQzMjEvYXV0aC92MSIsInN1YiI6ImYwNDBmNmY4LTA2YTUtNDA1My04YzQzLTcyMjBlZWMzZDMyZSIsImVtYWlsIjoidGVzdEBtYWlsLmNvbSIsInBob25lIjoiIiwiYXBwX21ldGFkYXRhIjp7InByb3ZpZGVyIjoiZW1haWwiLCJwcm92aWRlcnMiOlsiZW1haWwiXX0sInVzZXJfbWV0YWRhdGEiOnt9LCJyb2xlIjoiYXV0aGVudGljYXRlZCIsImFhbCI6ImFhbDEiLCJhbXIiOlt7Im1ldGhvZCI6InBhc3N3b3JkIiwidGltZXN0YW1wIjoxNzIzMTQzMDc0fV0sInNlc3Npb25faWQiOiJmOTY2M2ZhNi1jZmM4LTQyMTUtOTA5My0wZmE1Mjg1Y2RjNjQiLCJpc19hbm9ueW1vdXMiOmZhbHNlfQ.6CE6kvbj18ma2I_XcMIUXBP8yiX4-Rv9DN4fLoxfMtE"
    )

    channel: Channel = socket.channel(
        "test-topic", {"config": {"broadcast": {"self": True}}}
    )
    await channel.on_broadcast("test", callback=broadcast_callback).on_postgres_changes(
        "*", table="todos", callback=postgres_changes_callback
    ).on_postgres_changes(
        "INSERT", table="todos", callback=postgres_changes_insert_callback
    ).on_postgres_changes(
        "DELETE", table="todos", callback=postgres_changes_delete_callback
    ).on_postgres_changes(
        "UPDATE", table="todos", callback=postgres_changes_update_callback
    ).subscribe()

    await channel.send_broadcast("test", {"message": "Hello"})

    await socket.listen()


asyncio.run(main())
