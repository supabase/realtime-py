import os
from realtime.connection import Socket


def getSock():
    SUPABASE_ID = 'kzwoknoxuuvryajohvij'#os.getenv("SUPABASE_ID")
    API_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt6d29rbm94dXV2cnlham9odmlqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTcwODE5MDE3OCwiZXhwIjoyMDIzNzY2MTc4fQ.5CmeXUIg9mFBGF7ZPdE4Td5LdeL_mIx9h5rV0ptyPfQ'#os.getenv("API_KEY")
    print(SUPABASE_ID, API_KEY)
    URL = f"wss://{SUPABASE_ID}.supabase.co"
    s = Socket(URL, API_KEY)
    s.connect()

    return s


def test():
    sock = getSock()
    assert isinstance(sock, Socket)
