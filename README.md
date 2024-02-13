# realtime-py
Python Client Library to interface with the Phoenix Realtime Server 

## Requirements
**Python 3 higher**

## Installation
```bash
pip3 install realtime==1.0.2
```

## Installation from source 
```bash
poetry install
python3 usage.py 
```

## Quick Start 
```python
from realtime.connection import Socket
import asyncio

async def callback1(payload):
    print(f"Got message: {payload}")

async def main():

    # your phoenix server token
    TOKEN = ""
    # your phoenix server URL
    URL = f"ws://127.0.0.1:4000/socket/websocket?token={TOKEN}&vsn=2.0.0"

    client = Socket(URL)

    # connect to the server
    await client.connect()

    # fire and forget the listening routine
    listen_task = asyncio.ensure_future(client.listen())

    # join the channel
    channel = client.set_channel("this:is:my:topic")
    await channel.join()

    # by using a partial function
    channel.on("your_event_name", None, callback1)

    # we give it some time to complete
    await asyncio.sleep(10)

    # proper shut down
    listen_task.cancel()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())

    except KeyboardInterrupt:
        loop.stop()
        exit(0)
```

## Sending and Receiving data
Sending data to phoenix channels using `send`:
```python
await channel.send("your_handler", "this is my payload", None)
```
One can also use references for queries/answers:
```python

ref = 1
channel.on(None, ref, callback1)
await channel.send("your_handler", "this is my payload", ref)
# remove the callback when your are done
#                     |-> exercise left to the reader ;)
channel.off(None, ref, callback1)
```

##  Examples
see `usage.py`, `sending-receiving-usage.py`, and `fd-usage.py`.

## Sample usage with Supabase

Here's how you could connect to your realtime endpoint using Supabase endpoint. Should be correct as of 13th Feb 2024. Please replace `SUPABASE_ID` and `API_KEY` with your own `SUPABASE_ID` and `API_KEY`. The variables shown below are fake and they will not work if you try to run the snippet.

```python
from realtime.connection import Socket
import asyncio

SUPABASE_ID = "dlzlllxhaakqdmaapvji"
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlhdCI6MT"


async def callback1(payload):
    print("Callback 1: ", payload)

async def main():
    URL = f"wss://{SUPABASE_ID}.supabase.co/realtime/v1/websocket?apikey={API_KEY}&vsn=1.0.0"
    s = Socket(URL)
    await s.connect()
    listen_task = asyncio.ensure_future(s.listen())

    channel_1 = s.set_channel("realtime:*")
    await channel_1.join()
    channel_1.on("UPDATE", callback1)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())

    except KeyboardInterrupt:
        loop.stop()
        exit(0)
```

Then, go to the Supabase interface and toggle a row in a table. You should see a corresponding payload show up in your console/terminal.