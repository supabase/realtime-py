from urllib.parse import urlparse, urlunparse, urlencode

def http_to_websocket_url(url: str, params: dict = None) -> str:
    """
    Converts an HTTP URL to the corresponding WebSocket URL and appends query parameters.

    Example:
        Input: "https://example.com", {"apikey": "your_token"}
        Output: "wss://example.com/websocket?apikey=your_token"
    """
    parsed_url = urlparse(url)

    # Determine the scheme
    if parsed_url.scheme in ('http', 'ws'):
        scheme = 'ws'
    elif parsed_url.scheme in ('https', 'wss'):
        scheme = 'wss'
    else:
        raise ValueError(f"Unsupported URL scheme: {parsed_url.scheme}")

    # Ensure the path ends with '/websocket'
    path = parsed_url.path.rstrip('/')
    if not path.endswith('/websocket'):
        path += '/websocket'

    # Combine existing query parameters with new ones
    query_params = dict(param.split('=') for param in parsed_url.query.split('&') if param)
    if params:
        query_params.update(params)
    query_string = urlencode(query_params)

    # Construct the normalized WebSocket URL
    return urlunparse((scheme, parsed_url.netloc, path, '', query_string, ''))

