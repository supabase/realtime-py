import pytest
import os
from dotenv import load_dotenv

from realtime.connection import Socket

load_dotenv()

@pytest.fixture
def socket() -> Socket:
    return Socket(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY"))

def test_set_auth(socket: Socket):
    socket.connect()

    socket.set_auth("jwt")
    assert socket._access_token == "jwt"