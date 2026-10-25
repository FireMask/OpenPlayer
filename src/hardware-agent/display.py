"""Hilo de la pantalla (SPEC 17): player.subscribe → View → render → panel.show.
SPEC 18: modo del Service (displayMode), reloj automático, indicador de volumen y título con desplazamiento,
calculados en cada tick. También apaga el panel (DISPOFF) de noche o tras un rato detenida."""

import json
import logging
import socket
import threading
import time
from dataclasses import replace
from datetime import datetime

from cover import fetch_cover, prepare
from screen import View, render, title_overflow
from sender import connect_unix

log = logging.getLogger(__name__)

MAX_LINE_BYTES = 65536
STATES = ("playing", "paused", "stopped")
MODES = ("track", "clock", "art")
VOLUME_POPUP_SECONDS = 2
# Tabla propia: la Pi puede no tener el locale es instalado.
DAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_UNSET = object()
# Desplazamiento del título: 5 fps solo mientras se mueve. Medido en la Pi Zero 2 W (2026-10-24): 10 fps = 28 %
# de un núcleo, 5 fps = 14 %; cada cuadro completo cuesta ~27 ms de CPU (render 12 + RGB565 15).
# ponytail: cuadro completo por SPI; para más fps, enviar solo la franja del título (CASET/RASET parcial).
SCROLL_TICK = 0.2
SCROLL_SPEED = 30  # px/s
SCROLL_PAUSE = 1.0  # s quieto en cada extremo
WAKE_SECONDS = 10  # encendida tras un botón o al empezar a reproducir durante el horario nocturno
COVER_TICK = 0.1  # mientras carga la carátula: se ve apenas llega


class Display:
    def __init__(self, socket_path, panel, *, connect=None, tick_seconds=1.0, retry_seconds=2.0, label="",
                 idle_clock_seconds=60, night=None, off_after_stopped_minutes=None,
                 now=datetime.now, monotonic=time.monotonic, fetch=None):
        """panel: algo con init(), show(image), sleep_display() y wake_display().
        connect inyectable igual que Sender (TCP en pruebas). night: (inicio, fin) como datetime.time, o None.
        now (hora local, para el reloj) y monotonic (temporizadores) son inyectables para las pruebas.
        fetch: bytes de la carátula actual o None (SPEC 19); por defecto player.get_cover por connect."""
        self._path = socket_path
        self.panel = panel
        self._connect = connect or (lambda: connect_unix(socket_path))
        self._fetch = fetch or (lambda: fetch_cover(self._connect))
        self._tick = tick_seconds
        self._retry = retry_seconds
        self._label = label
        self._idle_clock = idle_clock_seconds
        self._night = night
        self._off_after = off_after_stopped_minutes * 60 if off_after_stopped_minutes else None
        self._now = now
        self._monotonic = monotonic
        self._stopping = threading.Event()
        self._base = View("offline")  # última vista recibida
        self._received = monotonic()  # cuándo llegó, para avanzar la posición localmente
        self._idle_since = None  # desde cuándo está en pausa o detenida
        self._stopped_since = None  # desde cuándo está detenida
        self._wake_until = 0.0  # hasta cuándo sigue encendida tras un botón
        self._panel_on = True
        self._volume = _UNSET  # volumen del snapshot anterior de esta conexión
        self._volume_until = 0.0  # hasta cuándo se ve el indicador de volumen
        self._scroll_title = None  # título que se está desplazando
        self._scroll_since = 0.0
        # Carátula (SPEC 19): solo la última, por (artista, álbum). Los escribe el hilo de la petición.
        self._cover_key = None
        self._cover = None
        self._cover_state = "none"  # "loading" | "ok" | "none"
        self._was_art = False
        self._shown = None
        self._thread = threading.Thread(target=self._run, name="display", daemon=True)

    def start(self):
        self._thread.start()

    def wake(self):
        """La llama el callback de cada botón: enciende el panel WAKE_SECONDS (se nota en el próximo tick)."""
        self._wake_until = self._monotonic() + WAKE_SECONDS

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
            tick = self._tick
            if self._scroll_title is not None:
                tick = SCROLL_TICK
            if self._cover_state == "loading":
                tick = min(tick, COVER_TICK)
            sock.settimeout(max(min(tick, 1 - elapsed % 1), 0.01))
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
        if view.status == "playing" and self._base.status != "playing":
            self._wake_until = now + WAKE_SECONDS  # de noche, empezar a reproducir también enciende
        if view.status in ("paused", "stopped"):
            if self._idle_since is None:
                self._idle_since = now
        else:
            self._idle_since = None
        if view.status == "stopped":
            if self._stopped_since is None:
                self._stopped_since = now
        else:
            self._stopped_since = None
        self._base = view
        self._received = now
        self._draw()

    def _draw(self):
        now = self._monotonic()
        if not self._power(now):
            return
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
        overflow = title_overflow(view.title)
        if view.status == "playing" and changes.get("mode", view.mode) == "track" and overflow:
            if self._scroll_title != view.title:
                self._scroll_title, self._scroll_since = view.title, now
            changes["scroll"] = scroll_offset(now - self._scroll_since, overflow)
        else:
            self._scroll_title = None
        art = changes.get("mode", view.mode) == "art" and view.status in STATES
        if art:
            self._update_cover(view)
            changes["cover"] = self._cover
        self._was_art = art
        view = replace(view, **changes)
        if view != self._shown:
            self.panel.show(render(view))
            self._shown = view


    def _update_cover(self, view):
        """Pide la carátula si cambió (artista, álbum) o al entrar al modo art sin una buena en caché."""
        key = (view.artist, view.album) if view.artist or view.album else (None, None, view.title)
        if not any(key):
            self._cover_key, self._cover, self._cover_state = None, None, "none"
            return
        if key == self._cover_key and (self._was_art or self._cover_state != "none"):
            return  # misma clave: en caché, cargando, o ya se sabe que no tiene (hasta salir y volver a entrar)
        self._cover_key, self._cover, self._cover_state = key, None, "loading"
        threading.Thread(target=self._load_cover, args=(key,), name="cover", daemon=True).start()

    def _load_cover(self, key):
        data = self._fetch()
        image = prepare(data) if data else None
        if self._cover_key == key:  # si la pista cambió mientras tanto, se descarta
            self._cover, self._cover_state = image, "ok" if image is not None else "none"

    def _power(self, now) -> bool:
        """Enciende o apaga el panel según el horario y la inactividad; True si está encendido."""
        night = self._night is not None and in_range(self._now().time(), *self._night)
        stopped = (self._off_after is not None and self._stopped_since is not None
                   and now - self._stopped_since >= self._off_after)
        on = not (night or stopped) or now < self._wake_until
        if on != self._panel_on:
            if on:
                self.panel.wake_display()
            else:
                self.panel.sleep_display()
                self._scroll_title = None  # sin cuadros mientras está apagada: tick normal
            self._panel_on = on
        return on


def in_range(t, start, end) -> bool:
    """start <= t < end; si start > end el rango cruza la medianoche."""
    return start <= t < end if start < end else t >= start or t < end


def scroll_offset(elapsed: float, overflow: int) -> int:
    """Pausa al inicio, avanza a SCROLL_SPEED hasta el final, pausa y vuelve al inicio."""
    travel = overflow / SCROLL_SPEED
    phase = elapsed % (SCROLL_PAUSE + travel + SCROLL_PAUSE)
    return min(int(max(phase - SCROLL_PAUSE, 0) * SCROLL_SPEED), overflow)


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
