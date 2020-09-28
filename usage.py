from connection import Socket

def callback1(msg):
    print("Callback 1: ", msg)

def callback2(msg):
    print("Callback 2: ", msg)

URL = "ws://localhost:4000/socket/websocket"
s = Socket(URL)
s.connect()
channel_1 = s.set_channel("realtime:public:todos")
channel_1.join().on("UPDATE", callback1)

channel_2 = s.set_channel("realtime:public:users")
channel_2.join().on("*", callback2)

if __name__ == "__main__":
    s.listen()