from constants import *

class RealtimeClient:
    def __init__(self, endpoint_url: str, **args):
        """
        Initializes the socket
        """
        self.endpoint = f"{endpoint_url}"
        pass

    def connect():
        """
        Connects to the socket 
        """
        pass

    def disconnect():
        """
        Disconnects the socket 
        """
        pass

    
    def log():
        """
        Logs the message
        """
        # [TODO](Joel) -- logs the message
        pass

    def on_open(callback):
        pass

    def on_error(callback):
        pass
    
    def on_messsage(callback):
        # Calls a function any time a message is received.
        pass

    def connection_state():
        pass

    def is_connected():
        return self.connection_state() == 'open'

    def remove(channel):
        """
        Removes a subscription from the socket.
        """
        pass
    
    def channel(topic, chan_params={}):
        pass
    
    def push(data):
        pass

    def on_conn_message(raw_message):
        pass

    def endpoint_url():
        """
        Returns the URL of the websocket
        """
        pass

    def make_ref():
        """
        Return the next message ref, accounting for overflows
        """
        pass

    def _on_conn_open():
        pass

    def _on_conn_close():
        pass

    def _on_conn_error():
        pass

    def _trigger_chan_error():
        pass

    def _append_params():
        pass
    
    def _flush_send_buffer():
        pass

    def _reset_heartbeat():
        pass

    def _send_heartbeat():
        pass

        



    

