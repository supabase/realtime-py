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