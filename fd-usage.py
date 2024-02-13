from realtime.connection import Socket
import asyncio
import uuid
import json
# We will use a partial function to pass the file descriptor to the callback
from functools import partial

# notice that the callback has two arguments
# and that it is not an async function
# it will be executed in a different thread
def callback(fd, payload):
    fd.write(json.dumps(payload))
    print(f"Callback with reference c2: {payload}")

async def main():

    # your phoenix server token
    TOKEN = ""
    # your phoenix server URL
    URL = f"ws://127.0.0.1:4000/socket/websocket?token={TOKEN}&vsn=2.0.0"

    # We create a file descriptor to write the received messages
    fd = create_file_and_return_fd()

    client = Socket(URL)

    # connect to the server
    await client.connect()

    # fire and forget the listening routine
    listen_task = asyncio.ensure_future(client.listen())

    # join the channel
    channel = client.set_channel("this:is:my:topic")
    await channel.join()

    # we can also use reference for the callback
    # with a proper reply elixir handler:
    #def handle_in("ping", payload, socket) do
    #   {:reply, {:ok, payload}, socket}
    # Here we use uuid, use whatever you want
    ref = str(uuid.uuid4())
    # Pass the file descriptor to the callback through a partial function
    channel.on(None, ref, partial(callback, fd))
    await channel.send("ping", "this is the ping payload that shall appear in myfile.txt", ref)

    # we give it some time to complete
    await asyncio.sleep(10)

    # proper shut down
    listen_task.cancel()
    fd.close()

def create_file_and_return_fd():
    fd = open("myfile.txt", "w")
    return fd

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())

    except KeyboardInterrupt:
        loop.stop()
        exit(0)