import http.client
import threading

import pytest

from ipc import IpcUnavailable
from server import BUTTON_NAMES, WebServer, is_allowed

SNAPSHOT = '{"type":"player.snapshot","state":"playing","trackTitle":"Á","volume":40}'
ERROR = '{"type":"error","request":"player.get_snapshot","message":"MPD did not respond"}'
OK = '{"type":"ok","request":"playlist.add"}'
PAGE = '{"type":"library.page","offset":0,"total":1,"entries":[{"uri":"Rock","directory":true}]}'


class FakeIpc:
    def __init__(self):
        self.pressed = []
        self.seeks = []
        self.reply = SNAPSHOT
        self.available = True

    def press(self, name):
        if not self.available:
            raise IpcUnavailable("down")
        self.pressed.append(name)

    def seek(self, seconds):
        if not self.available:
            raise IpcUnavailable("down")
        self.seeks.append(seconds)

    def snapshot(self):
        if not self.available:
            raise IpcUnavailable("down")
        return self.reply

    # Biblioteca y playlists: registra (método, argumentos) y responde library_reply.
    LIBRARY_METHODS = ("browse", "search", "play_track", "playlists", "playlist", "create_playlist",
                       "rename_playlist", "delete_playlist", "add_to_playlist", "remove_from_playlist",
                       "move_in_playlist", "play_playlist", "queue", "play_queue",
                       "remove_from_queue", "move_in_queue", "clear_queue")
    library_reply = OK
    library_calls = None

    def __getattr__(self, method):
        if method not in self.LIBRARY_METHODS:
            raise AttributeError(method)

        def call(*args):
            if not self.available:
                raise IpcUnavailable("down")
            if self.library_calls is None:
                self.library_calls = []
            self.library_calls.append((method, *args))
            return self.library_reply
        return call


@pytest.fixture
def web():
    ipc = FakeIpc()
    server = WebServer(0, ipc)
    # poll_interval corto: shutdown() espera un ciclo de sondeo (0.5 s por defecto) en cada prueba.
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    yield server, ipc
    server.shutdown()
    server.server_close()


def library_calls(ipc):
    return ipc.library_calls or []


def request(server, method, path, host="127.0.0.1", body=None):
    # Cliente IPv4 contra el socket dual stack: llega como ::ffff:127.0.0.1.
    conn = http.client.HTTPConnection(host, server.server_address[1], timeout=5)
    conn.request(method, path, body=body)
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response, body


def test_index_is_html(web):
    server, _ = web
    response, body = request(server, "GET", "/")

    assert response.status == 200
    assert response.getheader("Content-Type").startswith("text/html")
    assert b"OpenPlayer" in body and b"/api/buttons/" in body


@pytest.mark.parametrize("name", BUTTON_NAMES)
def test_button_press_returns_204_and_forwards(web, name):
    server, ipc = web
    response, body = request(server, "POST", f"/api/buttons/{name}")

    assert response.status == 204
    assert body == b""
    assert ipc.pressed == [name]


def test_unknown_button_is_404(web):
    server, ipc = web
    response, _ = request(server, "POST", "/api/buttons/shutdown")

    assert response.status == 404
    assert ipc.pressed == []


def test_button_with_service_down_is_503(web):
    server, ipc = web
    ipc.available = False

    assert request(server, "POST", "/api/buttons/next")[0].status == 503


def test_seek_returns_204_and_forwards(web):
    server, ipc = web
    response, body = request(server, "POST", "/api/seek", body=b'{"positionSeconds":83}')

    assert response.status == 204
    assert body == b""
    assert ipc.seeks == [83]


@pytest.mark.parametrize("body", [
    None,
    b"",
    b'{"positionSeconds":83,"pad":"' + b"x" * 1024 + b'"}',
    b"{positionSeconds:83}",
    b"\xff",
    b"[83]",
    b"{}",
    b'{"positionSeconds":"83"}',
    b'{"positionSeconds":83.5}',
    b'{"positionSeconds":true}',
    b'{"positionSeconds":-1}',
    b'{"positionSeconds":86401}',
])
def test_seek_invalid_body_is_400(web, body):
    server, ipc = web

    assert request(server, "POST", "/api/seek", body=body)[0].status == 400
    assert ipc.seeks == []


def test_seek_accepts_bounds(web):
    server, ipc = web
    for seconds in (0, 86400):
        assert request(server, "POST", "/api/seek", body=f'{{"positionSeconds":{seconds}}}'.encode())[0].status == 204
    assert ipc.seeks == [0, 86400]


def test_seek_with_service_down_is_503(web):
    server, ipc = web
    ipc.available = False

    assert request(server, "POST", "/api/seek", body=b'{"positionSeconds":83}')[0].status == 503


def test_snapshot_returns_line_as_json(web):
    server, _ = web
    response, body = request(server, "GET", "/api/snapshot")

    assert response.status == 200
    assert response.getheader("Content-Type").startswith("application/json")
    assert body.decode("utf-8") == SNAPSHOT


def test_snapshot_error_reply_is_502(web):
    server, ipc = web
    ipc.reply = ERROR
    response, body = request(server, "GET", "/api/snapshot")

    assert response.status == 502
    assert body.decode() == ERROR


def test_snapshot_with_service_down_is_503(web):
    server, ipc = web
    ipc.available = False

    assert request(server, "GET", "/api/snapshot")[0].status == 503


@pytest.mark.parametrize("method, path", [
    ("GET", "/api/buttons/next"),
    ("GET", "/api/seek"),
    ("POST", "/api/snapshot"),
    ("POST", "/"),
    ("DELETE", "/api/snapshot"),
])
def test_wrong_method_is_405(web, method, path):
    server, ipc = web

    assert request(server, method, path)[0].status == 405
    assert ipc.pressed == []


@pytest.mark.parametrize("path", ["/index.html", "/api", "/api/buttons/", "/../etc/passwd"])
def test_unknown_route_is_404(web, path):
    server, _ = web

    assert request(server, "GET", path)[0].status == 404


def test_query_string_is_ignored(web):
    server, _ = web

    assert request(server, "GET", "/api/snapshot?t=1")[0].status == 200


def test_ipv6_loopback_client(web):
    server, _ = web

    assert request(server, "GET", "/api/snapshot", host="::1")[0].status == 200


def test_disallowed_client_is_403_on_every_route(web):
    server, ipc = web
    server.is_allowed = lambda host: False

    for method, path in [("GET", "/"), ("GET", "/api/snapshot"), ("POST", "/api/buttons/next"), ("POST", "/api/seek"),
                         ("GET", "/x")]:
        assert request(server, method, path)[0].status == 403
    assert ipc.pressed == [] and ipc.seeks == []


@pytest.mark.parametrize("host, allowed", [
    ("127.0.0.1", True),
    ("10.1.2.3", True),
    ("172.16.0.1", True),
    ("172.31.255.255", True),
    ("192.168.18.75", True),
    ("::1", True),
    ("fe80::da3a:ddff:fe99:bbf2", True),
    ("fe80::1%wlan0", True),
    ("::ffff:192.168.1.20", True),
    ("::ffff:127.0.0.1", True),
    ("8.8.8.8", False),
    ("172.32.0.1", False),
    ("::ffff:8.8.8.8", False),
    ("2001:db8::1", False),
    ("fd00::1", False),
    ("not-an-ip", False),
])
def test_is_allowed(host, allowed):
    assert is_allowed(host) is allowed


# --- Biblioteca y playlists (SPEC 10) ---

QUERY_ROUTES = [
    ("/api/library", ("browse", "", 0)),
    ("/api/library?path=Rock%2FAC%20DC&offset=100", ("browse", "Rock/AC DC", 100)),
    ("/api/library/search?q=thunder", ("search", "thunder", 0)),
    ("/api/library/search?q=thunder&offset=200", ("search", "thunder", 200)),
    ("/api/playlists", ("playlists",)),
    ("/api/playlists/Viaje", ("playlist", "Viaje", 0)),
    ("/api/playlists/Viaje?offset=100", ("playlist", "Viaje", 100)),
    ("/api/playlists/Mi%20lista%20100%25", ("playlist", "Mi lista 100%", 0)),
    ("/api/queue", ("queue", 0)),
    ("/api/queue?offset=100", ("queue", 100)),
]


@pytest.mark.parametrize("path, expected", QUERY_ROUTES)
def test_library_queries_return_200_with_reply(web, path, expected):
    server, ipc = web
    ipc.library_reply = PAGE
    response, body = request(server, "GET", path)

    assert response.status == 200
    assert response.getheader("Content-Type").startswith("application/json")
    assert body.decode() == PAGE
    assert library_calls(ipc) == [expected]


MUTATION_ROUTES = [
    ("POST", "/api/library/play", b'{"uri":"Rock/a.flac"}', ("play_track", "Rock/a.flac")),
    ("POST", "/api/playlists", '{"name":"Ñandú \\"x\\""}'.encode(), ("create_playlist", 'Ñandú "x"')),
    ("POST", "/api/playlists/Viaje/rename", b'{"newName":"Gym"}', ("rename_playlist", "Viaje", "Gym")),
    ("DELETE", "/api/playlists/Mi%20lista", None, ("delete_playlist", "Mi lista")),
    ("POST", "/api/playlists/Viaje/tracks", b'{"uri":"Rock"}', ("add_to_playlist", "Viaje", "Rock")),
    ("DELETE", "/api/playlists/Viaje/tracks/3", None, ("remove_from_playlist", "Viaje", 3)),
    ("POST", "/api/playlists/Viaje/move", b'{"from":3,"to":2}', ("move_in_playlist", "Viaje", 3, 2)),
    ("POST", "/api/playlists/Viaje/play", b'{"position":4}', ("play_playlist", "Viaje", 4)),
    ("POST", "/api/playlists/Viaje/play", None, ("play_playlist", "Viaje", 0)),
    ("POST", "/api/playlists/Viaje/play", b"{}", ("play_playlist", "Viaje", 0)),
    ("POST", "/api/queue/play", b'{"position":3}', ("play_queue", 3)),
    ("DELETE", "/api/queue/tracks/17", None, ("remove_from_queue", 17)),
    ("POST", "/api/queue/move", b'{"id":17,"to":2}', ("move_in_queue", 17, 2)),
    ("DELETE", "/api/queue", None, ("clear_queue",)),
]


@pytest.mark.parametrize("method, path, body, expected", MUTATION_ROUTES)
def test_library_mutations_return_204(web, method, path, body, expected):
    server, ipc = web
    response, reply = request(server, method, path, body=body)

    assert response.status == 204
    assert reply == b""
    assert library_calls(ipc) == [expected]


BAD_REQUESTS = [
    ("GET", "/api/library?offset=-1", None),
    ("GET", "/api/library?offset=abc", None),
    ("GET", "/api/library?offset=1.5", None),
    ("GET", "/api/library/search", None),
    ("GET", "/api/library/search?q=", None),
    ("GET", "/api/playlists/Viaje?offset=x", None),
    ("POST", "/api/library/play", None),
    ("POST", "/api/library/play", b'{"uri":""}'),
    ("POST", "/api/library/play", b'{"uri":5}'),
    ("POST", "/api/library/play", b"{uri}"),
    ("POST", "/api/library/play", b"\xff"),
    ("POST", "/api/library/play", b'["Rock"]'),
    ("POST", "/api/library/play", b'{"uri":"' + b"x" * 4096 + b'"}'),
    ("POST", "/api/playlists", b"{}"),
    ("POST", "/api/playlists/Viaje/rename", b'{"name":"Gym"}'),
    ("POST", "/api/playlists/Viaje/tracks", None),
    ("DELETE", "/api/playlists/Viaje/tracks/-1", None),
    ("DELETE", "/api/playlists/Viaje/tracks/x", None),
    ("POST", "/api/playlists/Viaje/move", b'{"from":3}'),
    ("POST", "/api/playlists/Viaje/move", b'{"from":"3","to":2}'),
    ("POST", "/api/playlists/Viaje/move", b'{"from":true,"to":2}'),
    ("POST", "/api/playlists/Viaje/play", b'{"position":-1}'),
    ("POST", "/api/playlists/Viaje/play", b'{"position":1.5}'),
    ("DELETE", "/api/playlists/", None),
    ("POST", "/api/playlists//rename", b'{"newName":"Gym"}'),
    ("GET", "/api/queue?offset=-1", None),
    ("GET", "/api/queue?offset=x", None),
    ("POST", "/api/queue/play", None),
    ("POST", "/api/queue/play", b"{}"),
    ("POST", "/api/queue/play", b'{"position":-1}'),
    ("POST", "/api/queue/play", b'{"position":"3"}'),
    ("POST", "/api/queue/play", b'{"position":3.5}'),
    ("POST", "/api/queue/play", b'{"position":true}'),
    ("DELETE", "/api/queue/tracks/x", None),
    ("DELETE", "/api/queue/tracks/-1", None),
    ("DELETE", "/api/queue/tracks/", None),
    ("POST", "/api/queue/move", None),
    ("POST", "/api/queue/move", b'{"to":2}'),
    ("POST", "/api/queue/move", b'{"id":17}'),
    ("POST", "/api/queue/move", b'{"id":-1,"to":2}'),
    ("POST", "/api/queue/move", b'{"id":17,"to":-1}'),
    ("POST", "/api/queue/move", b'{"id":"17","to":2}'),
    ("POST", "/api/queue/move", b'{"id":17,"to":2.5}'),
    ("POST", "/api/queue/move", b'{"id":true,"to":2}'),
    ("POST", "/api/queue/move", b'{"id":17,"to":false}'),
]


@pytest.mark.parametrize("method, path, body", BAD_REQUESTS)
def test_library_invalid_request_is_400(web, method, path, body):
    server, ipc = web

    assert request(server, method, path, body=body)[0].status == 400
    assert library_calls(ipc) == []


@pytest.mark.parametrize("method, path, body", [
    ("GET", "/api/library", None),
    ("POST", "/api/playlists/Viaje/tracks", b'{"uri":"Rock"}'),
    ("GET", "/api/queue", None),
    ("POST", "/api/queue/play", b'{"position":99}'),
    ("DELETE", "/api/queue/tracks/99", None),
    ("POST", "/api/queue/move", b'{"id":99,"to":0}'),
    ("DELETE", "/api/queue", None),
])
def test_library_error_reply_is_502_with_line(web, method, path, body):
    server, ipc = web
    error = '{"type":"error","request":"playlist.add","message":"No such playlist"}'
    ipc.library_reply = error
    response, reply = request(server, method, path, body=body)

    assert response.status == 502
    assert reply.decode() == error


@pytest.mark.parametrize("method, path, body", [
    ("GET", "/api/playlists", None),
    ("POST", "/api/playlists", b'{"name":"Viaje"}'),
    ("GET", "/api/queue", None),
    ("POST", "/api/queue/play", b'{"position":3}'),
    ("DELETE", "/api/queue/tracks/17", None),
    ("POST", "/api/queue/move", b'{"id":17,"to":2}'),
    ("DELETE", "/api/queue", None),
])
def test_library_with_service_down_is_503(web, method, path, body):
    server, ipc = web
    ipc.available = False

    assert request(server, method, path, body=body)[0].status == 503


@pytest.mark.parametrize("method, path", [
    ("POST", "/api/library"),
    ("POST", "/api/library/search"),
    ("GET", "/api/library/play"),
    ("DELETE", "/api/playlists"),
    ("POST", "/api/playlists/Viaje"),
    ("GET", "/api/playlists/Viaje/rename"),
    ("GET", "/api/playlists/Viaje/tracks"),
    ("POST", "/api/playlists/Viaje/tracks/3"),
    ("DELETE", "/api/playlists/Viaje/move"),
    ("GET", "/api/playlists/Viaje/play"),
    ("POST", "/api/queue"),
    ("GET", "/api/queue/play"),
    ("PUT", "/api/queue"),
    ("GET", "/api/queue/move"),
    ("GET", "/api/queue/tracks/17"),
])
def test_library_wrong_method_is_405(web, method, path):
    server, ipc = web

    assert request(server, method, path)[0].status == 405
    assert library_calls(ipc) == []


@pytest.mark.parametrize("path", ["/api/library/x", "/api/playlists/Viaje/x", "/api/playlists/Viaje/tracks/3/x",
                                  "/api/queue/x", "/api/queue/tracks/17/x"])
def test_library_unknown_route_is_404(web, path):
    server, _ = web

    assert request(server, "GET", path)[0].status == 404


def test_library_disallowed_client_is_403(web):
    server, ipc = web
    server.is_allowed = lambda host: False

    for method, path in [("GET", "/api/library"), ("GET", "/api/playlists"), ("DELETE", "/api/playlists/Viaje")]:
        assert request(server, method, path)[0].status == 403
    assert library_calls(ipc) == []
