"""Hilo de la pantalla (SPEC 17): player.subscribe → View → render → panel.show.
SPEC 18: modo del Service (displayMode), reloj automático e indicador de volumen, calculados en cada tick."""

import json
import logging
import socket
import threading
import time
from dataclasses import replace
from datetime import datetime

from screen import View, render
from sender import connect_unix

log = logging.getLogger(__name__)

MAX_LINE_BYTES = 65536
STATES = ("playing", "paused", "stopped")
MODES = ("track", "clock")
VOLUME_POPUP_SECONDS = 2
# Tabla propia: la Pi puede no tener el locale es instalado.
DAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_UNSET = object()


class Display:
    def __init__(self, socket_path, panel, *, connect=None, tick_seconds=1.0, retry_seconds=2.0, label="",
                 idle_clock_seconds=60, now=datetime.now, monotonic=time.monotonic):
        """panel: algo con init() y show(image). connect inyectable igual que Sender (TCP en pruebas).
        now (hora local, para el reloj) y monotonic (temporizadores) son inyectables para las pruebas."""
        self._path = socket_path
        self.panel = panel
        self._connect = connect or (lambda: connect_unix(socket_path))
        self._tick = tick_seconds
        self._retry = retry_seconds
        self._label = label
        self._idle_clock = idle_clock_seconds
        self._now = now
        self._monotonic = monotonic
        self._stopping = threading.Event()
        self._base = View("offline")  # última vista recibida
        self._received = monotonic()  # cuándo llegó, para avanzar la posición localmente
        self._idle_since = None  # desde cuándo está en pausa o detenida
        self._volume = _UNSET  # volumen del snapshot anterior de esta conexión
        self._volume_until = 0.0  # hasta cuándo se ve el indicador de volumen
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
        self._volume = _UNSET  # el primer snapshot de la conexión no muestra el indicador
        while not self._stopping.is_set():
            # Despierta justo cuando la posición cambia de segundo, como mucho cada tick.
            elapsed = self._monotonic() - self._received
            sock.settimeout(max(min(self._tick, 1 - elapsed % 1), 0.01))
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
        now = self._monotonic()
        if view.status in STATES:
            if self._volume is not _UNSET and view.volume is not None and view.volume != self._volume:
                self._volume_until = now + VOLUME_POPUP_SECONDS
            self._volume = view.volume
        if view.status in ("paused", "stopped"):
            if self._idle_since is None:
                self._idle_since = now
        else:
            self._idle_since = None
        self._base = view
        self._received = now
        self._draw()

    def _draw(self):
        now = self._monotonic()
        view = self._base
        changes = {}
        if view.status == "playing" and view.position is not None:
            position = view.position + int(now - self._received)
            changes["position"] = min(position, view.duration) if view.duration else position
        idle = (self._idle_clock is not None and self._idle_since is not None
                and now - self._idle_since >= self._idle_clock)
        if view.mode == "clock" or idle:
            wall = self._now()
            changes.update(mode="clock", clock=f"{wall:%H:%M}",
                           date=f"{DAYS[wall.weekday()]} {wall.day} {MONTHS[wall.month - 1]}")
        if now < self._volume_until:
            changes["volume_popup"] = True
        view = replace(view, **changes)
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
    mode = message.get("displayMode")
    return View(
        state if state in STATES else "stopped",
        title=message.get("trackTitle"),
        artist=message.get("trackArtist"),
        album=message.get("trackAlbum"),
        position=message.get("positionSeconds"),
        duration=message.get("durationSeconds"),
        volume=message.get("volume"),
        queue_position=message.get("queuePosition"),
        queue_length=message.get("queueLength"),
        mode=mode if mode in MODES else "track",
    )
