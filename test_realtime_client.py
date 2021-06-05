from realtime_py.realtime_client import RealtimeClient
from realtime_py.connection import Socket


DEFAULT_URL = "wss://dlzlllxhaakqdmaapvji.supabase.co/realtime/v1/websocket?apikey=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlhdCI6MTYxNzI5MTcxMCwiZXhwIjoxOTMyODY3NzEwfQ.PeNcYi-bqVuinS2SKGlsElxwk982Xu5BtG3H4oN0aus&vsn=1.0.0"

socket = Socket(DEFAULT_URL)
realtime_subscription = RealtimeClient(
    DEFAULT_URL)
realtime_subscription.connect()
