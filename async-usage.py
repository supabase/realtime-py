from realtime.connection import Socket
import asyncio
import uuid

def callback1(payload):
    print(f"c1: {payload}")

def callback2(payload):
    print(f"c2: {payload}")


async def main():

    TOKEN = ""
    URLsink = f"ws://127.0.0.1:4000/socket/websocket?token={TOKEN}&vsn=2.0.0"

    client = Socket(URLsink)

    await client.connect()

    # fire and forget the listening routine
    listen_task = asyncio.ensure_future(client.listen())

    channel_s = client.set_channel("yourchannel")
    await channel_s.join()
    channel_s.on("test_event", None, callback1)

 # non sense elixir handler, we would not have an event on a reply
 #def handle_in("request_ping", payload, socket) do
 #   push(socket, "test_event", %{body: payload})
 #   {:noreply, socket}
 #end

    await channel_s.send("request_ping", "this is my payload 1", None)
    await channel_s.send("request_ping", "this is my payload 2", None)
    await channel_s.send("request_ping", "this is my payload 3", None)

 # proper relpy elixir handler
 #def handle_in("ping", payload, socket) do
 #   {:reply, {:ok, payload}, socket}
 #end

    ref = str(uuid.uuid4())
    channel_s.on(None, ref, callback2)
    await channel_s.send("ping", "this is my ping payload", ref)

    # we give it some time to complete
    await asyncio.sleep(15)

    # proper shut down
    listen_task.cancel()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
