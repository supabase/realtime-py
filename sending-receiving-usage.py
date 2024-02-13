from realtime.connection import Socket
import asyncio
import uuid

async def callback1(payload):
    print(f"c1: {payload}")

def callback2(payload):
    print(f"c2: {payload}")

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

    channel.on("test_event", None, callback1)

    # here is an example corresponding elixir handler for the sake of the example:
    #def handle_in("request_ping", payload, socket) do
    #   push(socket, "test_event", %{body: payload})
    #   {:noreply, socket}
    #end

    await channel.send("request_ping", "this is my payload 1", None)
    await channel.send("request_ping", "this is my payload 2", None)
    await channel.send("request_ping", "this is my payload 3", None)

    # we can also use reference for the callback
    # with a proper reply elixir handler:
    #def handle_in("ping", payload, socket) do
    #   {:reply, {:ok, payload}, socket}
    #end

    # Here we use uuid, use whatever you want
    ref = str(uuid.uuid4())
    channel.on(None, ref, callback2)
    await channel.send("ping", "this is my ping payload", ref)

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