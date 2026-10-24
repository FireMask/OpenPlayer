"""Envía button.pressed por el socket IPC (architecture.md §7) desde un hilo propio."""

import json
import logging
import queue
import select
import socket
import threading
import time

log = logging.getLogger(__name__)

# Cada cuánto se sondea, sin pulsaciones, si el Service cerró la conexión.
POLL_SECONDS = 1.0
SEND_TIMEOUT_SECONDS = 2.0


def connect_unix(path):
    """Conexión al socket del Service; también la usa la pantalla (display.py)."""
    if not hasattr(socket, "AF_UNIX"):
        raise OSError("AF_UNIX not supported on this platform")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
    except OSError:
        sock.close()
        raise
    return sock


class Sender:
    def __init__(self, socket_path, *, connect=None, min_backoff=0.5, max_backoff=10.0):
        self._path = socket_path
        # Inyectable: en Windows no hay AF_UNIX y las pruebas usan TCP local.
        self._connect = connect or (lambda: connect_unix(socket_path))
        self._min_backoff = min_backoff
        self._max_backoff = max_backoff
        self._backoff = min_backoff
        self._queue = queue.Queue()
        self._stopping = threading.Event()
        self._sock = None
        self._sequence = 0
        self._thread = threading.Thread(target=self._run, name="sender", daemon=True)

    def press(self, name):
        """Encola una pulsación. Thread-safe y nunca bloquea: lo llama el callback de GPIO."""
        self._queue.put(name)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stopping.set()
        self._queue.put(None)  # despierta al hilo si espera en la cola o en el backoff
        self._thread.join(timeout=5)

    def _run(self):
        try:
            while not self._stopping.is_set():
                if self._sock is None and not self._try_connect():
                    self._drop_for(self._backoff)
                    self._backoff = min(self._backoff * 2, self._max_backoff)
                    continue
                try:
                    name = self._queue.get(timeout=POLL_SECONDS)
                except queue.Empty:
                    if self._closed_by_peer():
                        self._disconnect()
                    continue
                if name is not None:
                    self._send(name)
        finally:
            if self._sock is not None:
                self._sock.close()

    def _try_connect(self):
        try:
            sock = self._connect()
        except OSError:
            return False
        sock.settimeout(SEND_TIMEOUT_SECONDS)
        self._sock = sock
        self._backoff = self._min_backoff
        log.info("connected to %s", self._path)
        return True

    def _drop_for(self, seconds):
        """Espera el backoff descartando las pulsaciones: no se reenvían al reconectar."""
        deadline = time.monotonic() + seconds
        while not self._stopping.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                name = self._queue.get(timeout=remaining)
            except queue.Empty:
                return
            if name is not None:
                log.warning("dropped %s: not connected", name)

    def _send(self, name):
        # El cierre del Service solo se nota al escribir dos veces; mirar antes evita perder esta pulsación.
        if self._closed_by_peer():
            self._disconnect()
            log.warning("dropped %s: not connected", name)
            return
        sequence = self._sequence + 1
        line = json.dumps({"type": "button.pressed", "button": name, "sequence": sequence},
                          separators=(",", ":")) + "\n"
        try:
            self._sock.sendall(line.encode("utf-8"))
        except OSError as e:
            log.warning("dropped %s: send failed (%s)", name, e)
            self._disconnect()
            return
        self._sequence = sequence
        log.info("button %s (sequence %d)", name, sequence)

    def _closed_by_peer(self):
        try:
            readable, _, _ = select.select([self._sock], [], [], 0)
            # El Service no responde a button.pressed: legible significa EOF o error.
            return bool(readable) and self._sock.recv(4096) == b""
        except OSError:
            return True

    def _disconnect(self):
        self._sock.close()
        self._sock = None
        log.warning("disconnected from %s", self._path)
