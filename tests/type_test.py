import os
from realtime.connection import Socket

def getSock():
    SUPABASE_ID = os.getenv("SUPABASE_ID") 
    API_KEY = os.getenv("API_KEY") 

    URL = f"wss://{SUPABASE_ID}.supabase.co/realtime/v1/websocket?apikey={API_KEY}&vsn=1.0.0"
    s = Socket(URL)
    s.connect()

    return s

def test():
    sock = getSock()
    assert isinstance(sock , Socket) == True
