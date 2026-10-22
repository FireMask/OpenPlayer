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


OK = '{"type":"ok","request":"playlist.add"}'

LIBRARY_CALLS = [
    (lambda i: i.browse("Rock/AC DC", 100), '{"type":"library.browse","path":"Rock/AC DC","offset":100}'),
    (lambda i: i.search("thunder", 0), '{"type":"library.search","query":"thunder","offset":0}'),
    (lambda i: i.play_track("Rock/a.flac"), '{"type":"library.play","uri":"Rock/a.flac"}'),
    (lambda i: i.playlists(), '{"type":"playlist.list"}'),
    (lambda i: i.playlist("Viaje", 0), '{"type":"playlist.get","name":"Viaje","offset":0}'),
    (lambda i: i.create_playlist("Viaje"), '{"type":"playlist.create","name":"Viaje"}'),
    (lambda i: i.rename_playlist("Viaje", "Gym"), '{"type":"playlist.rename","name":"Viaje","newName":"Gym"}'),
    (lambda i: i.delete_playlist("Viaje"), '{"type":"playlist.delete","name":"Viaje"}'),
    (lambda i: i.add_to_playlist("Viaje", "Rock"), '{"type":"playlist.add","name":"Viaje","uri":"Rock"}'),
    (lambda i: i.remove_from_playlist("Viaje", 3), '{"type":"playlist.remove","name":"Viaje","position":3}'),
    (lambda i: i.move_in_playlist("Viaje", 3, 2), '{"type":"playlist.move","name":"Viaje","from":3,"to":2}'),
    (lambda i: i.play_playlist("Viaje", 4), '{"type":"playlist.play","name":"Viaje","position":4}'),
    (lambda i: i.queue(100), '{"type":"queue.get","offset":100}'),
    (lambda i: i.play_queue(3), '{"type":"queue.play","position":3}'),
    (lambda i: i.remove_from_queue(17), '{"type":"queue.remove","id":17}'),
    (lambda i: i.move_in_queue(17, 2), '{"type":"queue.move","id":17,"to":2}'),
    (lambda i: i.clear_queue(), '{"type":"queue.clear"}'),
]


@pytest.mark.parametrize("call,expected", LIBRARY_CALLS)
def test_library_methods_send_exact_line_and_return_reply(server, call, expected):
    server.reply = OK.encode() + b"\n"

    assert call(Ipc("/x", connect=server.connect)) == OK
    assert wait_for(server.received) == [expected.encode() + b"\n"]


def test_request_returns_error_reply_unchanged(server):
    error = '{"type":"error","request":"playlist.create","message":"Playlist \'Viaje\' already exists"}'
    server.reply = error.encode() + b"\n"

    assert Ipc("/x", connect=server.connect).create_playlist("Viaje") == error


def test_request_accepts_reply_larger_than_snapshot_limit():
    big = '{"type":"library.page","entries":["' + "a" * 200_000 + '"]}'

    def send_big(conn):
        conn.sendall(big.encode() + b"\n")

    assert Ipc("/x", connect=one_shot_server(send_big)).playlists() == big


def test_request_reply_over_one_megabyte_is_unavailable():
    def send_huge(conn):
        try:
            conn.sendall(b"a" * (1024 * 1024 + 70_000))
        except OSError:
            pass  # el cliente cortó al pasar el límite

    with pytest.raises(IpcUnavailable):
        Ipc("/x", connect=one_shot_server(send_huge)).playlists()


def test_request_uses_library_timeout(server):
    server.reply = None
    start = time.monotonic()

    with pytest.raises(IpcUnavailable):
        Ipc("/x", connect=server.connect, timeout=5, library_timeout=0.3).playlists()
    assert time.monotonic() - start < 1.5


def test_default_library_timeout_is_five_seconds():
    import ipc
    assert ipc.LIBRARY_TIMEOUT_SECONDS == 5.0
    assert ipc.MAX_LIBRARY_REPLY_BYTES == 1024 * 1024


def test_request_connect_failure_is_unavailable():
    def refuse():
        raise ConnectionRefusedError("down")

    with pytest.raises(IpcUnavailable):
        Ipc("/x", connect=refuse).playlists()
