import http.client
import threading

import pytest

from ipc import IpcUnavailable
from server import BUTTON_NAMES, WebServer, is_allowed

SNAPSHOT = '{"type":"player.snapshot","state":"playing","trackTitle":"Á","volume":40}'
ERROR = '{"type":"error","request":"player.get_snapshot","message":"MPD did not respond"}'


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


@pytest.fixture
def web():
    ipc = FakeIpc()
    server = WebServer(0, ipc)
    # poll_interval corto: shutdown() espera un ciclo de sondeo (0.5 s por defecto) en cada prueba.
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    yield server, ipc
    server.shutdown()
    server.server_close()


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
