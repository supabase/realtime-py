from realtime.connection import Socket


def broadcast_callback(payload):
    print("broadcast: ", payload)
def presence_callback(payload):
    print("presence: ", payload)
def postgres_changes_callback(payload):
    print("postgres_changes: ", payload)

if __name__ == "__main__":
    URL = "wss://<project>.supabase.co"
    JWT = "<token>"
    s = Socket(URL, JWT)
    s.connect()

    channel = s.set_channel("broadcast-test",
                            {
                                "broadcast": { "ack": True, "self": True },
                                "postgres_changes": [
                                    {
                                    "event": "*",
                                    "schema": "public",
                                    "table": "*"
                                    }
                                    ]})
    channel.join().on("broadcast", dict(event ="test"), broadcast_callback)
    channel.join().on("presence", dict(event ="sync"), presence_callback)
    channel.join().on("postgres_changes", dict(event ="*"), postgres_changes_callback)

    s.listen()
