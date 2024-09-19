import asyncio
import datetime
import os

import aiohttp
import pytest
from dotenv import load_dotenv

from realtime import AsyncRealtimeClient
from realtime.types import RealtimeSubscribeStates

load_dotenv()

URL = os.getenv("SUPABASE_URL") or "http://127.0.0.1:54321"
ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ..."


async def get_access_token() -> str:
    url = f"{URL}/auth/v1/signup"
    headers = {"apikey": ANON_KEY, "Content-Type": "application/json"}
    email = (
        os.getenv("SUPABASE_TEST_EMAIL")
        or f"test_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}@example.com"
    )
    data = {
        "email": email,
        "password": os.getenv("SUPABASE_TEST_PASSWORD") or "test.123",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status in [200, 201]:
                json_response = await response.json()
                return json_response.get("access_token")
            else:
                raise Exception(
                    f"Failed to get access token. Status: {response.status}"
                )


@pytest.mark.asyncio
async def test_set_auth():
    socket = AsyncRealtimeClient(f"{URL}/realtime/v1", ANON_KEY)
    await socket.connect()
    await socket.set_auth("jwt")
    assert socket.access_token == "jwt"
    await socket.disconnect()


@pytest.mark.asyncio
async def test_broadcast_events(socket: AsyncRealtimeClient):
    await socket.connect()

    channel = socket.channel("test-broadcast", params={"broadcast": {"self": True}})
    received_events = []

    semaphore = asyncio.Semaphore(0)

    async def broadcast_callback(payload, ref):
        print("broadcast: ", payload)
        received_events.append(payload)
        semaphore.release()

    subscribed_event = asyncio.Event()

    async def subscribe_callback(state, error):
        if state == RealtimeSubscribeStates.SUBSCRIBED:
            subscribed_event.set()

    channel.on_broadcast("test-event", broadcast_callback)
    await channel.subscribe(subscribe_callback)

    await asyncio.wait_for(subscribed_event.wait(), 5)

    # Send 3 broadcast events
    for i in range(3):
        await channel.send_broadcast("test-event", {"message": f"Event {i+1}"})
        await asyncio.wait_for(semaphore.acquire(), 5)

    assert len(received_events) == 3
    assert received_events[0]["message"] == "Event 1"
    assert received_events[1]["message"] == "Event 2"
    assert received_events[2]["message"] == "Event 3"

    await socket.disconnect()


@pytest.mark.asyncio
async def test_postgres_changes():
    token = await get_access_token()

    socket = AsyncRealtimeClient(f"{URL}/realtime/v1", ANON_KEY)
    await socket.connect()
    await socket.set_auth(token)

    channel = socket.channel("test-postgres-changes")

    received_events = {"all": [], "INSERT": [], "UPDATE": [], "DELETE": []}

    insert_event = asyncio.Event()
    update_event = asyncio.Event()
    delete_event = asyncio.Event()
    subscribed_event = asyncio.Event()

    async def all_changes_callback(payload, ref):
        print("all_changes_callback: ", payload)
        received_events["all"].append(payload)

    async def insert_callback(payload, ref):
        print("insert_callback: ", payload)
        received_events["INSERT"].append(payload)
        insert_event.set()

    async def update_callback(payload, ref):
        print("update_callback: ", payload)
        received_events["UPDATE"].append(payload)
        update_event.set()

    async def delete_callback(payload, ref):
        print("delete_callback: ", payload)
        received_events["DELETE"].append(payload)
        delete_event.set()

    async def subscribe_callback(state, error):
        if state == RealtimeSubscribeStates.SUBSCRIBED:
            subscribed_event.set()

    channel.on_postgres_changes("*", all_changes_callback, table="todos")
    channel.on_postgres_changes("INSERT", insert_callback, table="todos")
    channel.on_postgres_changes("UPDATE", update_callback, table="todos")
    channel.on_postgres_changes("DELETE", delete_callback, table="todos")
    await channel.subscribe(subscribe_callback)

    # Wait for the channel to be subscribed
    await asyncio.wait_for(subscribed_event.wait(), 10)

    created_todo_id = await create_todo(
        token, {"description": "Test todo", "is_completed": False}
    )
    await asyncio.wait_for(insert_event.wait(), 10)

    await update_todo(
        token, created_todo_id, {"description": "Updated todo", "is_completed": True}
    )
    await asyncio.wait_for(update_event.wait(), 10)

    await delete_todo(token, created_todo_id)
    await asyncio.wait_for(delete_event.wait(), 10)

    assert len(received_events["all"]) == 3

    insert_event_data = received_events["all"][0]
    update_event_data = received_events["all"][1]
    delete_event_data = received_events["all"][2]

    assert insert_event_data["data"]["table"] == "todos"
    assert insert_event_data["data"]["eventType"] == "INSERT"
    assert insert_event_data["data"]["new"]["id"] == created_todo_id

    assert update_event_data["data"]["eventType"] == "UPDATE"
    assert update_event_data["data"]["new"]["id"] == created_todo_id

    assert delete_event_data["data"]["eventType"] == "DELETE"
    assert delete_event_data["data"]["old"]["id"] == created_todo_id

    assert received_events["INSERT"][0] == insert_event_data
    assert received_events["UPDATE"][0] == update_event_data
    assert received_events["DELETE"][0] == delete_event_data

    await socket.disconnect()


async def create_todo(access_token: str, todo: dict) -> str:
    url = f"{URL}/rest/v1/todos?select=id"
    headers = {
        "apikey": ANON_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.pgrst.object+json",
        "Prefer": "return=representation",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=todo) as response:
            if response.status == 201:
                json_response = await response.json()
                return json_response.get("id")
            else:
                raise Exception(
                    f"Failed to create todo. Status: {response.status}, {await response.text()}"
                )


async def update_todo(access_token: str, id: str, todo: dict):
    url = f"{URL}/rest/v1/todos?id=eq.{id}"
    headers = {
        "apikey": ANON_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.patch(url, headers=headers, json=todo) as response:
            if response.status != 204:
                raise Exception(
                    f"Failed to update todo. Status: {response.status}, {await response.text()}"
                )


async def delete_todo(access_token: str, id: str):
    url = f"{URL}/rest/v1/todos?id=eq.{id}"
    headers = {
        "apikey": ANON_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.delete(url, headers=headers) as response:
            if response.status != 204:
                raise Exception(
                    f"Failed to delete todo. Status: {response.status}, {await response.text()}"
                )
