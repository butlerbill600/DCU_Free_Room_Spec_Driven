import socket
import sys
import time
import pytest

from src.main import UvicornServerThread, find_free_port, wait_for_health_ok


def test_find_free_port():
    port = find_free_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535


def test_uvicorn_server_thread_lifecycle_and_health_poll():
    port = find_free_port()
    thread = UvicornServerThread("127.0.0.1", port)
    thread.start()

    url = f"http://127.0.0.1:{port}"
    health_ready = wait_for_health_ok(url, max_wait_seconds=5.0)
    assert health_ready is True

    thread.stop()
    thread.join(timeout=2.0)
    assert not thread.is_alive()


def test_uvicorn_server_thread_stdout_none_log_config(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    port = find_free_port()
    thread = UvicornServerThread("127.0.0.1", port)
    assert thread.server.config.log_config is None
