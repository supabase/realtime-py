import os

from realtime.connection import Socket


def getSock():
    SUPABASE_ID = os.getenv("SUPABASE_ID")
    API_KEY = os.getenv("API_KEY")


def getSock():
    SUPABASE_ID = os.getenv("SUPABASE_ID")
    API_KEY = os.getenv("API_KEY")
    print(SUPABASE_ID, API_KEY)
    URL = f"wss://{SUPABASE_ID}.supabase.co"
    s = Socket(URL, API_KEY)
    s.connect()

    return s


def test():
    sock = getSock()
    assert isinstance(sock, Socket)
