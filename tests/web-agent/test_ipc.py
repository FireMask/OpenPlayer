import socket
import threading
import time

import pytest

from ipc import Ipc, IpcUnavailable

SNAPSHOT = '{"type":"player.snapshot","state":"paused"}'


class FakeServer:
    """Servidor TCP local (en Windows no hay AF_UNIX): guarda lo recibido y responde `reply` por conexión."""

    def __init__(self, reply=None):
        self.reply = reply          # bytes a responder tras la primera línea; None = no responder
        self.received = []          # bytes completos recibidos por conexión (hasta EOF)
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._port = self._listener.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def connect(self):
        return socket.create_connection(("127.0.0.1", self._port), timeout=1)

    def close(self):
        self._listener.close()

    def _accept(self):
        while True:
            try:
                conn, _ = self._listener.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        data = b""
        with conn:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data and self.reply is not None:
                    conn.sendall(self.reply)
            self.received.append(data)


@pytest.fixture
def server():
    s = FakeServer()
    yield s
    s.close()


def wait_for(items, count=1, timeout=2.0):
    deadline = time.monotonic() + timeout
    while len(items) < count and time.monotonic() < deadline:
        time.sleep(0.01)
    return items


def test_press_sends_exact_line_and_closes(server):
    Ipc("/x", connect=server.connect).press("next")

    # El servidor solo registra al recibir EOF: que aparezca prueba que la conexión se cerró.
    assert wait_for(server.received) == [b'{"type":"button.pressed","button":"next"}\n']


def test_seek_sends_exact_line_and_closes(server):
    Ipc("/x", connect=server.connect).seek(83)

    assert wait_for(server.received) == [b'{"type":"player.seek","positionSeconds":83}\n']


def test_snapshot_returns_reply_line(server):
    server.reply = SNAPSHOT.encode() + b"\n"

    assert Ipc("/x", connect=server.connect).snapshot() == SNAPSHOT
    assert wait_for(server.received) == [b'{"type":"player.get_snapshot"}\n']


def test_snapshot_returns_error_reply_unchanged(server):
    error = '{"type":"error","request":"player.get_snapshot","message":"MPD unavailable"}'
    server.reply = error.encode() + b"\n"

    assert Ipc("/x", connect=server.connect).snapshot() == error


def one_shot_server(handle):
    """Acepta una conexión y la atiende con handle(conn); devuelve connect()."""
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]

    def run():
        conn, _ = listener.accept()
        with conn:
            conn.recv(4096)
            handle(conn)
        listener.close()

    threading.Thread(target=run, daemon=True).start()
    return lambda: socket.create_connection(("127.0.0.1", port), timeout=1)


def test_snapshot_reply_split_across_chunks():
    def send_in_two_parts(conn):
        conn.sendall(SNAPSHOT[:10].encode())
        time.sleep(0.1)
        conn.sendall(SNAPSHOT[10:].encode() + b"\n")

    assert Ipc("/x", connect=one_shot_server(send_in_two_parts)).snapshot() == SNAPSHOT


def test_connect_failure_is_unavailable():
    def refuse():
        raise ConnectionRefusedError("down")

    ipc = Ipc("/x", connect=refuse)
    with pytest.raises(IpcUnavailable):
        ipc.press("next")
    with pytest.raises(IpcUnavailable):
        ipc.seek(83)
    with pytest.raises(IpcUnavailable):
        ipc.snapshot()


def test_snapshot_without_reply_times_out(server):
    server.reply = None
    start = time.monotonic()

    with pytest.raises(IpcUnavailable):
        Ipc("/x", connect=server.connect, timeout=0.3).snapshot()
    assert time.monotonic() - start < 1.5


def test_default_timeout_is_two_seconds():
    import ipc
    assert ipc.TIMEOUT_SECONDS == 2.0


def test_snapshot_closed_without_reply_is_unavailable():
    with pytest.raises(IpcUnavailable):
        Ipc("/x", connect=one_shot_server(lambda conn: None)).snapshot()
