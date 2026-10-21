"""Servidor HTTP del web agent: página con los botones y API que reenvía al socket IPC (SPEC 08)."""

import ipaddress
import json
import logging
import os
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from ipc import IpcUnavailable

log = logging.getLogger(__name__)

BUTTON_NAMES = ("play_pause", "previous", "next", "volume_up", "volume_down", "menu", "refresh_library")
BUTTONS_PREFIX = "/api/buttons/"

# Solo red local; fe80::/10 porque Windows resuelve .local primero a IPv6 link-local (SPEC 07).
ALLOWED_NETWORKS = [ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fe80::/10")]

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"), "rb") as f:
    INDEX_HTML = f.read()


def is_allowed(host):
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])  # fe80::1%wlan0 → sin zona
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped  # socket dual stack: los clientes IPv4 llegan como ::ffff:a.b.c.d
    return any(ip in net for net in ALLOWED_NETWORKS)


class WebServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6
    daemon_threads = True

    def __init__(self, port, ipc, host="::"):
        self.ipc = ipc
        self.is_allowed = is_allowed  # reemplazable en pruebas
        super().__init__((host, port), Handler)

    def server_bind(self):
        # Dual stack: un solo socket en :: acepta IPv4 e IPv6.
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    server_version = "OpenPlayerWeb"
    sys_version = ""

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    def _handle(self, method):
        if not self.server.is_allowed(self.client_address[0]):
            log.warning("rejected client %s", self.client_address[0])
            return self._reply(HTTPStatus.FORBIDDEN)
        path = urlsplit(self.path).path
        if path == "/":
            if method != "GET":
                return self._reply(HTTPStatus.METHOD_NOT_ALLOWED)
            return self._reply(HTTPStatus.OK, INDEX_HTML, "text/html; charset=utf-8")
        if path == "/api/snapshot":
            if method != "GET":
                return self._reply(HTTPStatus.METHOD_NOT_ALLOWED)
            return self._snapshot()
        if path.startswith(BUTTONS_PREFIX) and path[len(BUTTONS_PREFIX):] in BUTTON_NAMES:
            if method != "POST":
                return self._reply(HTTPStatus.METHOD_NOT_ALLOWED)
            return self._press(path[len(BUTTONS_PREFIX):])
        self._reply(HTTPStatus.NOT_FOUND)

    def _press(self, name):
        try:
            self.server.ipc.press(name)
        except IpcUnavailable as e:
            log.warning("dropped %s: %s", name, e)
            return self._reply(HTTPStatus.SERVICE_UNAVAILABLE)
        log.info("button %s", name)
        self._reply(HTTPStatus.NO_CONTENT)

    def _snapshot(self):
        try:
            line = self.server.ipc.snapshot()
        except IpcUnavailable as e:
            log.warning("snapshot unavailable: %s", e)
            return self._reply(HTTPStatus.SERVICE_UNAVAILABLE)
        try:
            kind = json.loads(line).get("type")
        except (ValueError, AttributeError):
            kind = None
        status = HTTPStatus.OK if kind == "player.snapshot" else HTTPStatus.BAD_GATEWAY
        self._reply(status, line.encode("utf-8"), "application/json; charset=utf-8")

    def _reply(self, status, body=b"", content_type="text/plain; charset=utf-8"):
        if not body and status != HTTPStatus.NO_CONTENT:
            body = f"{status.value} {status.phrase}\n".encode()
        self.send_response(status)
        if status != HTTPStatus.NO_CONTENT:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if status != HTTPStatus.NO_CONTENT:
            self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # sin log por pedido: el sondeo cada 2 s llenaría el journal
