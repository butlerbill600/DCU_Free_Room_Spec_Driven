import socket
import time
import pytest
from httpx import AsyncClient, ASGITransport

from src.main import UvicornServerThread, find_free_port


def test_find_free_port():
    port = find_free_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535


def test_uvicorn_server_thread_lifecycle():
    port = find_free_port()
    thread = UvicornServerThread("127.0.0.1", port)
    thread.start()

    time.sleep(0.3)
    assert thread.is_alive()

    # Verify socket connection succeeds
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        conn = s.connect_ex(("127.0.0.1", port))
        assert conn == 0

    thread.stop()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
