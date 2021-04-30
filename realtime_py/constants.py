VSN_STRING = '1.0.0'
DEFAULT_TIMEOUT = 10000
WS_CLOSE_NORMAL = 1000


# TODO eventually substitute all these constants with enum. See: https://github.com/supabase/realtime-js/blob/master/src/lib/constants.ts
SOCKET_CONNECTING= 0
SOCKET_OPEN = 1
SOCKET_CLOSING =2
SOCKET_CLOSED = 3

# Channel states 
CHANNEL_STATE_CLOSED = 'closed'
CHANNEL_STATE_ERRORED = 'errored'
CHANNEL_STATE_JOINED = 'joined'
CHANNEL_STATE_JOINING = 'joining'
CHANNEL_STATE_LEAVING = 'leaving'

# Channel events
CHANNEL_EVENT_CLOSE = 'phx_close'
CHANNEL_EVENT_ERROR = 'phx_error'
CHANNEL_EVENT_JOIN = 'phx_join'
CHANNEL_EVENT_REPLY = 'phx_reply'
CHANNEL_EVENT_LEAVE = 'phx_leave'

# Transports
TRANSPORT_WEBSOCKET = 'websocket'

