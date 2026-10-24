"""Hilo de la pantalla (SPEC 17): player.subscribe → View → render → panel.show."""

import json
import logging
import socket
import threading
import time
from dataclasses import replace

from screen import View, render
from sender import connect_unix

log = logging.getLogger(__name__)

MAX_LINE_BYTES = 65536
STATES = ("playing", "paused", "stopped")


class Display:
    def __init__(self, socket_path, panel, *, connect=None, tick_seconds=1.0, retry_seconds=2.0, label=""):
        """panel: algo con init() y show(image). connect inyectable igual que Sender (TCP en pruebas)."""
        self._path = socket_path
        self.panel = panel
        self._connect = connect or (lambda: connect_unix(socket_path))
        self._tick = tick_seconds
        self._retry = retry_seconds
        self._label = label
        self._stopping = threading.Event()
        self._base = View("offline")  # última vista recibida
        self._received = time.monotonic()  # cuándo llegó, para avanzar la posición localmente
        self._shown = None
        self._thread = threading.Thread(target=self._run, name="display", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        """Espera a que termine el show() en curso; el llamador cierra después el panel."""
        self._stopping.set()
        self._thread.join(timeout=5)

    def _run(self):
        try:
            self.panel.init()
            self._draw()  # "Sin conexión" hasta el primer snapshot; también valida la fuente
        except Exception as e:
            log.error("display init failed: %s", e)
            return
        log.info("display ready%s", f" ({self._label})" if self._label else "")
        try:
            while not self._stopping.is_set():
                try:
                    sock = self._subscribe()
                except OSError:
                    self._set(View("offline"))
                    self._stopping.wait(self._retry)
                    continue
                try:
                    self._read(sock)
                except OSError:
                    pass
                finally:
                    sock.close()
                if not self._stopping.is_set():
                    log.warning("display: disconnected from %s", self._path)
                    self._set(View("offline"))
                    self._stopping.wait(self._retry)
        except Exception as e:
            log.error("display failed: %s", e)

    def _subscribe(self):
        sock = self._connect()
        try:
            sock.sendall(b'{"type":"player.subscribe"}\n')
        except OSError:
            sock.close()
            raise
        return sock

    def _read(self, sock):
        """Lee líneas hasta que el Service corta; entre líneas, despierta en cada tick para avanzar la posición."""
        pending = b""
        while not self._stopping.is_set():
            elapsed = time.monotonic() - self._received
            sock.settimeout(self._tick - elapsed % self._tick)
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                self._draw()
                continue
            if not chunk:
                return
            *lines, pending = (pending + chunk).split(b"\n")
            if len(pending) > MAX_LINE_BYTES:
                raise OSError("subscription line too long")
            for line in lines:
                view = parse(line)
                if view is not None:
                    self._set(view)

    def _set(self, view):
        self._base = view
        self._received = time.monotonic()
        self._draw()

    def _draw(self):
        view = self._base
        if view.status == "playing" and view.position is not None:
            position = view.position + int((time.monotonic() - self._received) / self._tick)
            if view.duration:
                position = min(position, view.duration)
            view = replace(view, position=position)
        if view != self._shown:
            self.panel.show(render(view))
            self._shown = view


def parse(line: bytes) -> View | None:
    """player.snapshot / error del Service → View; cualquier otra línea se ignora."""
    try:
        message = json.loads(line)
    except ValueError:
        log.warning("display: ignored invalid line")
        return None
    if not isinstance(message, dict):
        return None
    if message.get("type") == "error":
        return View("mpd_error")
    if message.get("type") != "player.snapshot":
        return None
    state = message.get("state")
    return View(
        state if state in STATES else "stopped",
        title=message.get("trackTitle"),
        artist=message.get("trackArtist"),
        position=message.get("positionSeconds"),
        duration=message.get("durationSeconds"),
        volume=message.get("volume"),
    )
