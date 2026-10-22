"""Servidor HTTP del web agent: página con los botones y API que reenvía al socket IPC (SPEC 08 a 11)."""

import ipaddress
import json
import logging
import os
import queue
import socket
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from ipc import IpcUnavailable

log = logging.getLogger(__name__)

BUTTON_NAMES = ("play_pause", "previous", "next", "volume_up", "volume_down", "menu", "refresh_library")
BUTTONS_PREFIX = "/api/buttons/"
MAX_BODY_BYTES = 1024
MAX_SEEK_SECONDS = 86400
MAX_LIBRARY_BODY_BYTES = 4096
MAX_EVENT_CLIENTS = 8
PING_SECONDS = 15
RESUBSCRIBE_SECONDS = 2

# Solo red local; fe80::/10 porque Windows resuelve .local primero a IPv6 link-local (SPEC 07).
ALLOWED_NETWORKS = [ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fe80::/10")]

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"), "rb") as f:
    INDEX_HTML = f.read()


class Events:
    """Última línea del Service y una cola por página abierta (queue.Queue(maxsize=16)); cola llena → la página se descarta.

    Un hilo de fondo mantiene la suscripción IPC (SPEC 16) mientras corre el web agent."""

    def __init__(self, ipc, resubscribe=RESUBSCRIBE_SECONDS):
        self._ipc = ipc
        self._resubscribe = resubscribe
        self._lock = threading.Lock()
        self.latest = None
        self.clients = set()

    def start(self):
        threading.Thread(target=self._run, name="events", daemon=True).start()

    def connect(self):
        """Cola nueva con la última línea, o None si ya hay MAX_EVENT_CLIENTS páginas."""
        with self._lock:
            if len(self.clients) >= MAX_EVENT_CLIENTS:
                return None
            q = queue.Queue(maxsize=16)
            if self.latest is not None:
                q.put_nowait(self.latest)
            self.clients.add(q)
            return q

    def disconnect(self, q):
        with self._lock:
            self.clients.discard(q)

    def _run(self):
        while True:
            try:
                for line in self._ipc.subscribe():
                    self._publish(line)
            except IpcUnavailable as e:
                log.warning("subscription unavailable: %s", e)
                # La misma línea de error que ya entiende la página (→ "Sin conexión con el reproductor").
                self._publish(json.dumps({"type": "error", "request": "player.get_snapshot", "message": str(e)},
                                         separators=(",", ":")))
            time.sleep(self._resubscribe)

    def _publish(self, line):
        with self._lock:
            self.latest = line
            for q in list(self.clients):
                try:
                    q.put_nowait(line)
                except queue.Full:
                    log.warning("event client too slow; dropped")
                    self.clients.discard(q)


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

    def __init__(self, port, ipc, host="::", events=None):
        self.ipc = ipc
        self.events = events or Events(ipc)  # main.py la arranca; las pruebas publican a mano
        self.is_allowed = is_allowed  # reemplazable en pruebas
        self.ping_seconds = PING_SECONDS  # reemplazable en pruebas
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
        if path == "/api/events":
            if method != "GET":
                return self._reply(HTTPStatus.METHOD_NOT_ALLOWED)
            return self._events()
        if path.startswith(BUTTONS_PREFIX) and path[len(BUTTONS_PREFIX):] in BUTTON_NAMES:
            if method != "POST":
                return self._reply(HTTPStatus.METHOD_NOT_ALLOWED)
            return self._press(path[len(BUTTONS_PREFIX):])
        if path == "/api/seek":
            if method != "POST":
                return self._reply(HTTPStatus.METHOD_NOT_ALLOWED)
            return self._seek()
        routes = self._library_routes(path)
        if routes is not None:
            if method not in routes:
                return self._reply(HTTPStatus.METHOD_NOT_ALLOWED)
            return self._library(routes[method])
        self._reply(HTTPStatus.NOT_FOUND)

    def _library_routes(self, path):
        """Rutas de biblioteca, playlists (SPEC 10) y cola (SPEC 11 a 13): {método: () -> línea IPC}, o None si la ruta no existe.

        Cada función valida la forma del pedido y lanza ValueError (→ 400); el Core valida el contenido."""
        ipc = self.server.ipc
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        if path == "/api/library":
            return {"GET": lambda: ipc.browse(_param(query, "path", ""), _offset(query))}
        if path == "/api/library/search":
            return {"GET": lambda: ipc.search(_nonempty(_param(query, "q"), "q"), _offset(query))}
        if path == "/api/library/play":
            return {"POST": lambda: ipc.play_track(_text(self._json_body(), "uri"))}
        if path == "/api/queue":
            return {"GET": lambda: ipc.queue(_offset(query)), "DELETE": ipc.clear_queue}
        if path == "/api/queue/play":
            return {"POST": lambda: ipc.play_queue(_int(self._json_body(), "position"))}
        if path == "/api/queue/move":
            def move_queue():
                body = self._json_body()
                return ipc.move_in_queue(_int(body, "id"), _int(body, "to"))
            return {"POST": move_queue}
        if path == "/api/queue/tracks":
            def add_queue():
                body = self._json_body()
                return ipc.add_to_queue(_text(body, "uri"), _bool(body, "next"))
            return {"POST": add_queue}
        if path == "/api/queue/save":
            return {"POST": lambda: ipc.save_queue(_text(self._json_body(), "name"))}
        if path.startswith("/api/queue/tracks/"):
            song_id = path[len("/api/queue/tracks/"):]
            return None if "/" in song_id else {"DELETE": lambda: ipc.remove_from_queue(_index(song_id))}
        if path == "/api/playlists":
            return {"GET": ipc.playlists, "POST": lambda: ipc.create_playlist(_text(self._json_body(), "name"))}
        if not path.startswith("/api/playlists/"):
            return None
        # Partir antes de decodificar: un %2F en el nombre no crea un segmento nuevo.
        parts = [unquote(p) for p in path[len("/api/playlists/"):].split("/")]
        action = parts[1:]

        def name():
            return _nonempty(parts[0], "name")

        if not action:
            return {"GET": lambda: ipc.playlist(name(), _offset(query)),
                    "DELETE": lambda: ipc.delete_playlist(name())}
        if action == ["rename"]:
            return {"POST": lambda: ipc.rename_playlist(name(), _text(self._json_body(), "newName"))}
        if action == ["tracks"]:
            return {"POST": lambda: ipc.add_to_playlist(name(), _text(self._json_body(), "uri"))}
        if len(action) == 2 and action[0] == "tracks":
            return {"DELETE": lambda: ipc.remove_from_playlist(name(), _index(action[1]))}
        if action == ["move"]:
            def move():
                body = self._json_body()
                return ipc.move_in_playlist(name(), _int(body, "from"), _int(body, "to"))
            return {"POST": move}
        if action == ["play"]:
            return {"POST": lambda: ipc.play_playlist(name(), _int(self._json_body(optional=True), "position", 0))}
        return None

    def _library(self, call):
        try:
            line = call()
        except ValueError:
            return self._reply(HTTPStatus.BAD_REQUEST)
        except IpcUnavailable as e:
            log.warning("library request unavailable: %s", e)
            return self._reply(HTTPStatus.SERVICE_UNAVAILABLE)
        try:
            kind = json.loads(line).get("type")
        except (ValueError, AttributeError):
            kind = None
        if kind == "ok":
            return self._reply(HTTPStatus.NO_CONTENT)
        status = HTTPStatus.BAD_GATEWAY if kind in ("error", None) else HTTPStatus.OK
        self._reply(status, line.encode("utf-8"), "application/json; charset=utf-8")

    def _json_body(self, optional=False):
        """Objeto JSON del cuerpo (≤ 4 KB); ValueError si falta o es inválido. optional: sin cuerpo → {}."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid Content-Length") from None
        if length == 0 and optional:
            return {}
        if not 0 < length <= MAX_LIBRARY_BODY_BYTES:
            raise ValueError("body missing or too large")  # sin leer: no aceptamos cuerpos arbitrarios
        body = json.loads(self.rfile.read(length))  # JSONDecodeError y UnicodeDecodeError son ValueError
        if not isinstance(body, dict):
            raise ValueError("body is not an object")
        return body

    def _press(self, name):
        try:
            self.server.ipc.press(name)
        except IpcUnavailable as e:
            log.warning("dropped %s: %s", name, e)
            return self._reply(HTTPStatus.SERVICE_UNAVAILABLE)
        log.info("button %s", name)
        self._reply(HTTPStatus.NO_CONTENT)

    def _seek(self):
        seconds = self._read_seek_seconds()
        if seconds is None:
            return self._reply(HTTPStatus.BAD_REQUEST)
        try:
            self.server.ipc.seek(seconds)
        except IpcUnavailable as e:
            log.warning("dropped seek %s: %s", seconds, e)
            return self._reply(HTTPStatus.SERVICE_UNAVAILABLE)
        log.info("seek %s", seconds)
        self._reply(HTTPStatus.NO_CONTENT)

    def _read_seek_seconds(self):
        """positionSeconds del cuerpo JSON, o None si el cuerpo es inválido."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if not 0 < length <= MAX_BODY_BYTES:
            return None  # sin leer: no aceptamos cuerpos arbitrarios
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:  # incluye UnicodeDecodeError
            return None
        seconds = body.get("positionSeconds") if isinstance(body, dict) else None
        # bool es subclase de int: true no es un número de segundos.
        if type(seconds) is not int or not 0 <= seconds <= MAX_SEEK_SECONDS:
            return None
        return seconds

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

    def _events(self):
        """SSE (SPEC 16): la última línea conocida, luego una por cambio y ": ping" si no hay nada en ping_seconds."""
        events = self.server.events
        q = events.connect()
        if q is None:
            return self._reply(HTTPStatus.SERVICE_UNAVAILABLE)
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            while q in events.clients:  # Events la quita si se llenó: la página no leía
                try:
                    chunk = f"data: {q.get(timeout=self.server.ping_seconds)}\n\n"
                except queue.Empty:
                    chunk = ": ping\n\n"  # también detecta páginas cerradas: la escritura falla
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except OSError:
            pass  # página cerrada
        finally:
            events.disconnect(q)
            self.close_connection = True

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


def _nonempty(value, field):
    """Cadena no vacía; longitud y caracteres permitidos los valida el Core."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid {field}")
    return value


def _text(body, field):
    return _nonempty(body.get(field), field)


def _int(body, field, default=None):
    """Entero JSON ≥ 0; bool no cuenta. Si falta y hay default, el default."""
    if field not in body and default is not None:
        return default
    value = body.get(field)
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid {field}")
    return value


def _bool(body, field):
    """Booleano JSON opcional (False si falta); 1 o "true" no cuentan."""
    value = body.get(field, False)
    if type(value) is not bool:
        raise ValueError(f"invalid {field}")
    return value


def _index(text):
    """Entero ≥ 0 escrito en la ruta o en la query."""
    if not text.isascii() or not text.isdigit():
        raise ValueError("invalid index")
    return int(text)


def _param(query, name, default=None):
    values = query.get(name)
    if not values:
        if default is None:
            raise ValueError(f"missing {name}")
        return default
    return values[0]


def _offset(query):
    return _index(_param(query, "offset", "0"))
