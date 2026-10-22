"""Cliente del socket IPC (architecture.md §7): una conexión por pedido, sin estado."""

import json
import socket

TIMEOUT_SECONDS = 2.0
MAX_REPLY_BYTES = 65536
# Biblioteca y playlists (SPEC 10): lsinfo/search sobre miles de pistas tardan más y responden más.
LIBRARY_TIMEOUT_SECONDS = 5.0
MAX_LIBRARY_REPLY_BYTES = 1024 * 1024


class IpcUnavailable(Exception):
    """El Service no acepta la conexión o no responde a tiempo."""


class Ipc:
    def __init__(self, socket_path, *, connect=None, timeout=TIMEOUT_SECONDS,
                 library_timeout=LIBRARY_TIMEOUT_SECONDS):
        self._path = socket_path
        self._timeout = timeout
        self._library_timeout = library_timeout
        # Inyectable: en Windows no hay AF_UNIX y las pruebas usan TCP local.
        self._connect = connect or self._connect_unix

    def press(self, name):
        with self._open() as sock:
            self._send(sock, {"type": "button.pressed", "button": name})

    def seek(self, seconds):
        with self._open() as sock:
            self._send(sock, {"type": "player.seek", "positionSeconds": seconds})

    def snapshot(self):
        """Devuelve la línea de respuesta (player.snapshot o error) sin el salto de línea."""
        with self._open(self._timeout) as sock:
            self._send(sock, {"type": "player.get_snapshot"})
            return self._read_line(sock, MAX_REPLY_BYTES)

    def subscribe(self):
        """Suscripción (SPEC 16): genera cada línea (player.snapshot o error) a medida que llega.

        IpcUnavailable si no conecta o se corta. Sin timeout de lectura: entre cambios puede pasar cualquier tiempo."""
        with self._open() as sock:
            self._send(sock, {"type": "player.subscribe"})
            sock.settimeout(None)
            pending = b""
            while True:
                try:
                    chunk = sock.recv(65536)
                except OSError as e:
                    raise IpcUnavailable(f"subscription failed: {e}") from e
                if not chunk:
                    raise IpcUnavailable("subscription closed")
                *lines, pending = (pending + chunk).split(b"\n")
                if len(pending) > MAX_REPLY_BYTES:
                    raise IpcUnavailable("subscription line too long")
                for line in lines:
                    yield line.decode("utf-8")

    def request(self, message):
        """Envía un mensaje de biblioteca/playlists/cola y devuelve su línea de respuesta (ok, página, lista o error)."""
        with self._open(self._library_timeout) as sock:
            self._send(sock, message)
            return self._read_line(sock, MAX_LIBRARY_REPLY_BYTES)

    def browse(self, path, offset):
        return self.request({"type": "library.browse", "path": path, "offset": offset})

    def search(self, query, offset):
        return self.request({"type": "library.search", "query": query, "offset": offset})

    def play_track(self, uri):
        return self.request({"type": "library.play", "uri": uri})

    def playlists(self):
        return self.request({"type": "playlist.list"})

    def playlist(self, name, offset):
        return self.request({"type": "playlist.get", "name": name, "offset": offset})

    def create_playlist(self, name):
        return self.request({"type": "playlist.create", "name": name})

    def rename_playlist(self, name, new_name):
        return self.request({"type": "playlist.rename", "name": name, "newName": new_name})

    def delete_playlist(self, name):
        return self.request({"type": "playlist.delete", "name": name})

    def add_to_playlist(self, name, uri):
        return self.request({"type": "playlist.add", "name": name, "uri": uri})

    def remove_from_playlist(self, name, position):
        return self.request({"type": "playlist.remove", "name": name, "position": position})

    def move_in_playlist(self, name, from_position, to_position):
        return self.request({"type": "playlist.move", "name": name, "from": from_position, "to": to_position})

    def play_playlist(self, name, position):
        return self.request({"type": "playlist.play", "name": name, "position": position})

    def queue(self, offset):
        return self.request({"type": "queue.get", "offset": offset})

    def play_queue(self, position):
        return self.request({"type": "queue.play", "position": position})

    def remove_from_queue(self, song_id):
        return self.request({"type": "queue.remove", "id": song_id})

    def move_in_queue(self, song_id, to_position):
        return self.request({"type": "queue.move", "id": song_id, "to": to_position})

    def clear_queue(self):
        return self.request({"type": "queue.clear"})

    def add_to_queue(self, uri, next_):
        return self.request({"type": "queue.add", "uri": uri, "next": next_})

    def save_queue(self, name):
        return self.request({"type": "queue.save", "name": name})

    def _open(self, timeout=None):
        try:
            sock = self._connect()
        except OSError as e:
            raise IpcUnavailable(f"cannot connect to {self._path}: {e}") from e
        sock.settimeout(timeout or self._timeout)
        return sock

    @staticmethod
    def _read_line(sock, max_bytes):
        reply = b""
        try:
            while b"\n" not in reply:
                chunk = sock.recv(65536)
                if not chunk or len(reply) > max_bytes:
                    raise IpcUnavailable("connection closed without a reply")
                reply += chunk
        except OSError as e:  # incluye socket.timeout
            raise IpcUnavailable(f"no reply: {e}") from e
        return reply.split(b"\n", 1)[0].decode("utf-8")

    def _send(self, sock, message):
        line = json.dumps(message, separators=(",", ":")) + "\n"
        try:
            sock.sendall(line.encode("utf-8"))
        except OSError as e:
            raise IpcUnavailable(f"send failed: {e}") from e

    def _connect_unix(self):
        if not hasattr(socket, "AF_UNIX"):
            raise OSError("AF_UNIX not supported on this platform")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self._path)
        except OSError:
            sock.close()
            raise
        return sock
