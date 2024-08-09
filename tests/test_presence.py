import asyncio
import os

import pytest
from dotenv import load_dotenv
from realtime.channel import Channel

from realtime.connection import Socket

load_dotenv()


@pytest.fixture
def socket() -> Socket:
    url = f"{os.getenv("SUPABASE_URL")}/realtime/v1"
    key = os.getenv("SUPABASE_ANON_KEY")
    return Socket(url, key)


# @pytest.mark.asyncio
# async def test_presence(socket: Socket):
#     await socket.connect()

#     channel: Channel = socket.channel("room")

#     def on_sync():
#         print("on_sync", channel.presence.state)

#     def on_join():
#         print("on_join", channel.presence.state)

#     def on_leave():
#         print("on_leave", channel.presence.state)

#     await channel.on_presence_sync(on_sync).on_presence_join(on_join).on_presence_leave(on_leave).subscribe()

