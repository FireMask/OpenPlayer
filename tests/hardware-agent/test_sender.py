import json
import logging
import socket
import threading
import time

import pytest

from sender import Sender


def wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met within timeout")


class FakeServer:
    """Servidor TCP local: en Windows no hay AF_UNIX; el stream tiene la misma semántica."""

    def __init__(self):
        self.available = True
        self.attempts = []          # instantes de cada intento de conexión
        self.connections = []       # sockets aceptados
        self.lines = []             # (índice de conexión, mensaje JSON)
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._port = self._listener.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def connect(self):
        self.attempts.append(time.monotonic())
        if not self.available:
            raise ConnectionRefusedError("fake server unavailable")
        return socket.create_connection(("127.0.0.1", self._port), timeout=1)

    def close_connections(self):
        for conn in self.connections:
            # close() solo no cierra mientras el makefile del lector siga abierto; shutdown envía FIN ya.
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()

    def close(self):
        self.close_connections()
        self._listener.close()

    def _accept(self):
        while True:
            try:
                conn, _ = self._listener.accept()
            except OSError:
                return
            self.connections.append(conn)
            threading.Thread(target=self._read, args=(len(self.connections) - 1, conn), daemon=True).start()

    def _read(self, index, conn):
        with conn.makefile("r", encoding="utf-8") as f:
            try:
                for line in f:
                    self.lines.append((index, line))
            except OSError:
                pass


class BrokenSocket:
    """Socket real (select funciona) cuyo envío falla."""

    def __init__(self, sock):
        self._sock = sock

    def fileno(self):
        return self._sock.fileno()

    def settimeout(self, value):
        self._sock.settimeout(value)

    def recv(self, size):
        return self._sock.recv(size)

    def sendall(self, data):
        raise BrokenPipeError("broken")

    def close(self):
        self._sock.close()


@pytest.fixture
def server():
    s = FakeServer()
    yield s
    s.close()


@pytest.fixture
def make_sender(server):
    senders = []

    def make(**kwargs):
        sender = Sender("/run/openplayer/hardware.sock", connect=kwargs.pop("connect", server.connect), **kwargs)
        senders.append(sender)
        sender.start()
        return sender

    yield make
    for sender in senders:
        sender.stop()


def test_sends_exact_lines_with_incrementing_sequence(server, make_sender):
    sender = make_sender()
    wait_until(lambda: server.connections)

    sender.press("next")
    sender.press("play_pause")

    wait_until(lambda: len(server.lines) == 2)
    assert [line for _, line in server.lines] == [
        '{"type":"button.pressed","button":"next","sequence":1}\n',
        '{"type":"button.pressed","button":"play_pause","sequence":2}\n',
    ]


def test_press_without_server_returns_immediately_and_is_dropped(server, make_sender, caplog):
    caplog.set_level(logging.INFO)
    server.available = False
    sender = make_sender(min_backoff=0.05, max_backoff=0.05)

    start = time.monotonic()
    sender.press("next")
    assert time.monotonic() - start < 0.05
    wait_until(lambda: "dropped next: not connected" in caplog.text)

    server.available = True
    wait_until(lambda: server.connections)
    sender.press("menu")

    wait_until(lambda: server.lines)
    time.sleep(0.2)
    assert [json.loads(line)["button"] for _, line in server.lines] == ["menu"]
    assert json.loads(server.lines[0][1])["sequence"] == 1


def test_detects_idle_close_and_reconnects(server, make_sender, caplog):
    caplog.set_level(logging.INFO)
    sender = make_sender(min_backoff=0.05)
    wait_until(lambda: len(server.connections) == 1)

    closed_at = time.monotonic()
    server.close_connections()

    wait_until(lambda: "disconnected from" in caplog.text, timeout=2)
    assert time.monotonic() - closed_at <= 2
    wait_until(lambda: len(server.connections) == 2)
    sender.press("previous")
    wait_until(lambda: server.lines)
    assert server.lines[0][0] == 1


def test_send_error_drops_event_and_reconnects(server, make_sender, caplog):
    caplog.set_level(logging.INFO)
    calls = []

    def connect():
        sock = server.connect()
        calls.append(sock)
        return BrokenSocket(sock) if len(calls) == 1 else sock

    sender = make_sender(connect=connect, min_backoff=0.05)
    wait_until(lambda: calls)

    sender.press("next")
    wait_until(lambda: "dropped next: send failed" in caplog.text)
    wait_until(lambda: len(calls) == 2)
    sender.press("volume_up")

    wait_until(lambda: server.lines)
    assert server.lines[0][1] == '{"type":"button.pressed","button":"volume_up","sequence":1}\n'


def test_backoff_grows_up_to_max_and_resets_after_connect(server, make_sender):
    server.available = False
    make_sender(min_backoff=0.02, max_backoff=0.08)
    wait_until(lambda: len(server.attempts) >= 6)

    gaps = [b - a for a, b in zip(server.attempts, server.attempts[1:])]
    assert gaps[0] < 0.06
    assert max(gaps) < 0.08 + 0.05
    assert gaps[-1] >= 0.07

    server.available = True
    wait_until(lambda: server.connections)
    server.available = False
    count = len(server.attempts)
    server.close_connections()
    wait_until(lambda: len(server.attempts) >= count + 2)

    first_gap = server.attempts[count + 1] - server.attempts[count]
    assert first_gap < 0.06


def test_stop_ends_thread_even_during_long_backoff(server, make_sender):
    server.available = False
    sender = make_sender(min_backoff=10, max_backoff=10)
    wait_until(lambda: server.attempts)

    start = time.monotonic()
    sender.stop()

    assert not sender._thread.is_alive()
    assert time.monotonic() - start < 1
