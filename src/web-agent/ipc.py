"""Cliente del socket IPC (architecture.md §7): una conexión por pedido, sin estado."""

import json
import socket

TIMEOUT_SECONDS = 2.0
MAX_REPLY_BYTES = 65536


class IpcUnavailable(Exception):
    """El Service no acepta la conexión o no responde a tiempo."""


class Ipc:
    def __init__(self, socket_path, *, connect=None, timeout=TIMEOUT_SECONDS):
        self._path = socket_path
        self._timeout = timeout
        # Inyectable: en Windows no hay AF_UNIX y las pruebas usan TCP local.
        self._connect = connect or self._connect_unix

    def press(self, name):
        with self._open() as sock:
            self._send(sock, {"type": "button.pressed", "button": name})

    def snapshot(self):
        """Devuelve la línea de respuesta (player.snapshot o error) sin el salto de línea."""
        with self._open() as sock:
            self._send(sock, {"type": "player.get_snapshot"})
            reply = b""
            try:
                while b"\n" not in reply:
                    chunk = sock.recv(4096)
                    if not chunk or len(reply) > MAX_REPLY_BYTES:
                        raise IpcUnavailable("connection closed without a reply")
                    reply += chunk
            except OSError as e:  # incluye socket.timeout
                raise IpcUnavailable(f"no reply: {e}") from e
        return reply.split(b"\n", 1)[0].decode("utf-8")

    def _open(self):
        try:
            sock = self._connect()
        except OSError as e:
            raise IpcUnavailable(f"cannot connect to {self._path}: {e}") from e
        sock.settimeout(self._timeout)
        return sock

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
