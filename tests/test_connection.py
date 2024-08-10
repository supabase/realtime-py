import asyncio
import datetime
import os

import aiohttp
import pytest
from dotenv import load_dotenv

from realtime.channel import Channel, RealtimeSubscribeStates
from realtime.connection import Socket

load_dotenv()


URL = os.getenv("SUPABASE_URL") or "http://127.0.0.1:54321"
ANON_KEY = (
    os.getenv("SUPABASE_ANON_KEY")
    or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
)


@pytest.fixture
def socket() -> Socket:
    url = f"{URL}/realtime/v1"
    key = ANON_KEY
    return Socket(url, key)


async def access_token() -> str:
    url = f"{URL}/auth/v1/signup"
    headers = {"apikey": ANON_KEY, "Content-Type": "application/json"}
    data = {
        "email": os.getenv("SUPABASE_TEST_EMAIL")
        or f"test_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}@example.com",
        "password": os.getenv("SUPABASE_TEST_PASSWORD") or "test.123",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                json_response = await response.json()
                return json_response.get("access_token")
            else:
                raise Exception(
                    f"Failed to get access token. Status: {response.status}"
                )


@pytest.mark.asyncio
async def test_set_auth(socket: Socket):
    await socket.connect()

    await socket.set_auth("jwt")
    assert socket.access_token == "jwt"

    await socket.close()


@pytest.mark.asyncio
async def test_broadcast_events(socket: Socket):
    await socket.connect()
    listen_task = asyncio.create_task(socket.listen())

    channel = socket.channel(
        "test-broadcast", params={"config": {"broadcast": {"self": True}}}
    )
    received_events = []

    semaphore = asyncio.Semaphore(0)

    def broadcast_callback(payload):
        print("broadcast: ", payload)
        received_events.append(payload)
        semaphore.release()

    subscribe_event = asyncio.Event()
    await channel.on_broadcast("test-event", broadcast_callback).subscribe(
        lambda state, error: (
            subscribe_event.set()
            if state == RealtimeSubscribeStates.SUBSCRIBED
            else None
        )
    )

    await asyncio.wait_for(subscribe_event.wait(), 5)

    # Send 3 broadcast events
    for i in range(3):
        await channel.send_broadcast("test-event", {"message": f"Event {i+1}"})
        await asyncio.wait_for(semaphore.acquire(), 5)

    assert len(received_events) == 3
    assert received_events[0]["payload"]["message"] == "Event 1"
    assert received_events[1]["payload"]["message"] == "Event 2"
    assert received_events[2]["payload"]["message"] == "Event 3"

    await socket.close()
    listen_task.cancel()


@pytest.mark.asyncio
async def test_postgrest_changes(socket: Socket):
    token = await access_token()

    await socket.connect()
    listen_task = asyncio.create_task(socket.listen())

    await socket.set_auth(token)

    channel: Channel = socket.channel("test-postgres-changes")
    received_events = {"all": [], "insert": [], "update": [], "delete": []}

    def all_changes_callback(payload):
        print("all_changes_callback: ", payload)
        received_events["all"].append(payload)

    insert_event = asyncio.Event()

    def insert_callback(payload):
        print("insert_callback: ", payload)
        received_events["insert"].append(payload)
        insert_event.set()

    update_event = asyncio.Event()

    def update_callback(payload):
        print("update_callback: ", payload)
        received_events["update"].append(payload)
        update_event.set()

    delete_event = asyncio.Event()

    def delete_callback(payload):
        print("delete_callback: ", payload)
        received_events["delete"].append(payload)
        delete_event.set()

    subscribed_event = asyncio.Event()

    await channel.on_postgres_changes(
        "*", all_changes_callback, table="todos"
    ).on_postgres_changes("INSERT", insert_callback, table="todos").on_postgres_changes(
        "UPDATE", update_callback, table="todos"
    ).on_postgres_changes(
        "DELETE", delete_callback, table="todos"
    ).subscribe(
        lambda state, error: (
            subscribed_event.set()
            if state == RealtimeSubscribeStates.SUBSCRIBED
            else None
        )
    )

    # Wait for the channel to be subscribed
    await asyncio.wait_for(subscribed_event.wait(), 5)

    created_todo_id = await create_todo(
        token, {"description": "Test todo", "is_completed": False}
    )
    await asyncio.wait_for(insert_event.wait(), 5)

    await update_todo(
        token, created_todo_id, {"description": "Updated todo", "is_completed": True}
    )
    await asyncio.wait_for(update_event.wait(), 5)

    await delete_todo(token, created_todo_id)
    await asyncio.wait_for(delete_event.wait(), 5)

    assert len(received_events["all"]) == 3

    insert = received_events["all"][0]
    update = received_events["all"][1]
    delete = received_events["all"][2]

    assert insert["data"]["record"]["id"] == created_todo_id
    assert insert["data"]["record"]["description"] == "Test todo"
    assert insert["data"]["record"]["is_completed"] == False

    assert update["data"]["record"]["id"] == created_todo_id
    assert update["data"]["record"]["description"] == "Updated todo"
    assert update["data"]["record"]["is_completed"] == True

    assert delete["data"]["old_record"]["id"] == created_todo_id

    assert received_events["insert"] == [insert]
    assert received_events["update"] == [update]
    assert received_events["delete"] == [delete]

    await socket.close()
    listen_task.cancel()


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
                raise Exception(f"Failed to create todo. Status: {response.status}")


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
                raise Exception(f"Failed to update todo. Status: {response.status}")


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
                raise Exception(f"Failed to delete todo. Status: {response.status}")
