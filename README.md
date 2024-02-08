# realtime-py
Python Client Library to interface with the Phoenix Realtime Server 

## Requirements
**Python 3 higher**

## Installation
```bash
pip3 install realtime==1.0.2
```

## Installation from source 
```bash
pip3 install -r requirements.txt
python3 usage.py 

```

## Quick Start 
```python
from realtime.connection import Socket

def callback1(payload):
    print("Callback 1: ", payload)

def callback2(payload):
    print("Callback 2: ", payload)

if __name__ == "__main__":
    URL = "ws://localhost:4000/socket/websocket"
    s = Socket(URL)
    s.connect()

    channel_1 = s.set_channel("realtime:public:todos")
    channel_1.join().on("UPDATE", callback1)

    channel_2 = s.set_channel("realtime:public:users")
    channel_2.join().on("*", callback2)

    s.listen()
```



## Sample usage with Supabase

Here's how you could connect to your realtime endpoint using Supabase endpoint. Correct as of 5th June 2021. Please replace `SUPABASE_ID` and `API_KEY` with your own `SUPABASE_ID` and `API_KEY`. The variables shown below are fake and they will not work if you try to run the snippet.

```python
from realtime.connection import Socket

SUPABASE_ID = "dlzlllxhaakqdmaapvji"
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlhdCI6MT"


def callback1(payload):
    print("Callback 1: ", payload)

if __name__ == "__main__":
    URL = f"wss://{SUPABASE_ID}.supabase.co/realtime/v1/websocket?apikey={API_KEY}&vsn=1.0.0"
    s = Socket(URL)
    s.connect()

    channel_1 = s.set_channel("realtime:*")
    channel_1.join().on("UPDATE", callback1)
    s.listen()

```

Then, go to the Supabase interface and toggle a row in a table. You should see a corresponding payload show up in your console/terminal.



