__all__ = [
    "DEFAULT_HEADERS"
]

from .version import __version__

DEFAULT_HEADERS = {
    "X-Client-Info": f"gotrue-py/{__version__}"
}
