# realtime-py
Python Client Library to interface with the Phoenix Realtime Server 

## Requirements
**Python 3 higher**

## Installation
```bash
pip3 install realtime_py==0.1.1a0
```

## Installation from source 
```bash
pip3 install -r requirements.txt
python3 usage.py 

```

## Quick Start 
```python
from realtime_py.connection import Socket

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


