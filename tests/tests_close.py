import os

from realtime.connection import Socket


def callback(payload):
    print("Callback:\t", payload)


def test():
    SUPABASE_ID = os.environ.get("SUPABASE_TEST_URL")
    API_KEY = os.environ.get("SUPABASE_TEST_KEY")

    URL = f"wss://{SUPABASE_ID}.supabase.co/realtime/v1/websocket?apikey={API_KEY}&vsn=1.0.0"

    s = Socket(URL)
    s.connect()

    channel_1 = s.set_channel("realtime:public:sample")
    channel_1.join().on("INSERT", callback)

    s.close()
    assert s.ws_connection.closed, "Connection was not closed as expected."


if __name__ == "__main__":
    test()
