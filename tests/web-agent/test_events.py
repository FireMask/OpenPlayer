import queue
import socket
import time

import pytest

from ipc import Ipc
from server import MAX_EVENT_CLIENTS, Events

A = '{"type":"player.snapshot","state":"playing"}'
B = '{"type":"player.snapshot","state":"paused"}'


class FakeService:
    """Service falso por TCP (en Windows no hay AF_UNIX): la prueba acepta y escribe a mano."""

    def __init__(self):
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._listener.settimeout(5)
        self.port = self._listener.getsockname()[1]
        self.up = True

    def connect(self):
        if not self.up:
            raise ConnectionRefusedError("down")
        return socket.create_connection(("127.0.0.1", self.port), timeout=1)

    def accept(self):
        """Acepta la suscripción y devuelve la conexión tras leer su línea."""
        conn, _ = self._listener.accept()
        conn.settimeout(5)
        assert conn.recv(4096) == b'{"type":"player.subscribe"}\n'
        return conn

    def close(self):
        self._listener.close()


@pytest.fixture
def service():
    s = FakeService()
    yield s
    s.close()


def started(service, resubscribe=0.05):
    events = Events(Ipc("/x", connect=service.connect), resubscribe=resubscribe)
    events.start()
    return events


def wait_until(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.01)
    return condition()


def test_each_line_goes_to_every_page(service):
    events = started(service)
    pages = [events.connect(), events.connect()]
    conn = service.accept()

    conn.sendall((A + "\n" + B + "\n").encode())

    for page in pages:
        assert page.get(timeout=2) == A
        assert page.get(timeout=2) == B
    conn.close()


def test_new_page_gets_latest_line_first(service):
    events = started(service)
    conn = service.accept()
    conn.sendall((A + "\n" + B + "\n").encode())
    assert wait_until(lambda: events.latest == B)

    page = events.connect()

    assert page.get_nowait() == B
    conn.close()


def test_service_down_publishes_error_and_resubscribes(service):
    events = started(service)
    page = events.connect()
    service.accept().close()

    error = page.get(timeout=2)
    assert error.startswith('{"type":"error","request":"player.get_snapshot","message":')
    conn = service.accept()  # reintenta solo
    conn.sendall((A + "\n").encode())
    assert page.get(timeout=2) == A
    conn.close()


def test_service_refusing_keeps_publishing_error_until_back(service):
    service.up = False
    events = started(service)
    page = events.connect()

    assert page.get(timeout=2).startswith('{"type":"error"')
    assert page.get(timeout=2).startswith('{"type":"error"')  # sigue reintentando
    service.up = True
    conn = service.accept()
    conn.sendall((A + "\n").encode())
    assert wait_until(lambda: events.latest == A)
    conn.close()


def test_full_queue_drops_only_that_page(service):
    events = started(service)
    slow = events.connect()
    conn = service.accept()

    for _ in range(17):
        conn.sendall((A + "\n").encode())
    assert wait_until(lambda: slow not in events.clients)

    page = events.connect()
    conn.sendall((B + "\n").encode())
    assert wait_until(lambda: not page.empty() and list(page.queue)[-1] == B)
    conn.close()


def test_connect_is_capped():
    events = Events(ipc=None)
    pages = [events.connect() for _ in range(MAX_EVENT_CLIENTS)]

    assert None not in pages
    assert events.connect() is None
    events.disconnect(pages[0])
    assert isinstance(events.connect(), queue.Queue)
