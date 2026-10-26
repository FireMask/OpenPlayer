"""Menú en pantalla (SPEC 21): Biblioteca, Listas, Cola y Apagar, navegado con los nombres menu_* de gestures.py.

Máquina de estados sin GPIO ni dibujo. Los pedidos IPC corren en run() (un hilo aparte: un MPD lento no frena la
cuenta de apagado); sus respuestas se aplican solo si su nivel sigue arriba de la pila.
Los callbacks (changed, toast) se llaman fuera del lock: redibujan y el dibujo vuelve a pedir view().
"""

import threading
import time

from screen import MenuView

PAGE_AHEAD = 10  # pide la página siguiente con el cursor a ≤ 10 filas del final de lo cargado


def _in_thread(job):
    threading.Thread(target=job, name="menu", daemon=True).start()


def _basename(uri):
    return uri.rstrip("/").rsplit("/", 1)[-1]


def _label(entry):
    return entry.get("title") or _basename(entry.get("uri") or "")


class _Row:
    def __init__(self, label, action):
        self.label = label
        self.action = action  # tupla: ("browse", path), ("add", uri, next), …


class _Level:
    def __init__(self, title, rows=(), load=None, parse=None):
        self.title = title
        self.rows = list(rows)  # filas fijas primero ("▶ Reproducir todo"), luego las cargadas
        self.cursor = 0
        self.load = load  # offset → pedido IPC; None en los niveles fijos
        self.parse = parse  # (respuesta, offset) → (filas, total)
        self.fetched = 0  # filas cargadas por load (sin las fijas): el offset de la página siguiente
        self.total = None  # None: todavía no se sabe
        self.loading = False


class Menu:
    def __init__(self, request, *, power_off, toast, changed, queue_position=lambda: None,
                 run=_in_thread, monotonic=time.monotonic, timeout=30):
        self._request = request
        self._power_off = power_off
        self._toast = toast
        self._changed = changed
        self._queue_position = queue_position
        self._run = run
        self._monotonic = monotonic
        self._timeout = timeout
        self._lock = threading.Lock()
        self._stack = []  # vacío = cerrado
        self._last = 0.0  # último botón, para el timeout

    @property
    def is_open(self):
        with self._lock:
            return bool(self._stack) and not self._expired()

    def open(self):
        with self._lock:
            self._last = self._monotonic()
            self._stack = [_Level("Menú", [
                _Row("Biblioteca", ("browse", "")),
                _Row("Listas", ("playlists",)),
                _Row("Cola", ("queue",)),
                _Row("Apagar", ("confirm_off",)),
            ])]
        self._changed()

    def close(self):
        with self._lock:
            self._stack = []
        self._changed()

    def up(self):
        self._move(-1)

    def down(self):
        self._move(1)

    def back(self):
        with self._lock:
            if not self._touch():
                return
            self._stack.pop()
        self._changed()

    def select(self):
        with self._lock:
            if not self._touch():
                return
            level = self._stack[-1]
            if not level.rows:
                return
            action = level.rows[level.cursor].action
        self._do(action)

    def view(self, t):
        """None si está cerrado; cierra (sin changed: lo llama quien dibuja) si pasó el timeout."""
        with self._lock:
            if not self._stack:
                return None
            if self._expired(t):
                self._stack = []
                return None
            level = self._stack[-1]
            return MenuView(level.title, tuple(row.label for row in level.rows), level.cursor,
                            loading=level.loading and not level.rows)

    # Bajo el lock

    def _expired(self, t=None):
        return (self._monotonic() if t is None else t) - self._last >= self._timeout

    def _touch(self):
        """Un botón: renueva el timeout. False si el menú está cerrado (o venció)."""
        if not self._stack or self._expired():
            self._stack = []
            return False
        self._last = self._monotonic()
        return True

    def _next_page(self, level):
        """El offset a pedir si el cursor está cerca del final de lo cargado y falta; si no, None."""
        if (level.load is None or level.loading or level.total is None
                or level.fetched >= level.total or len(level.rows) - 1 - level.cursor > PAGE_AHEAD):
            return None
        level.loading = True
        return level.fetched

    # Fuera del lock

    def _move(self, step):
        with self._lock:
            if not self._touch():
                return
            level = self._stack[-1]
            cursor = max(0, min(level.cursor + step, len(level.rows) - 1))
            moved = cursor != level.cursor
            level.cursor = cursor
            offset = self._next_page(level)
        if offset is not None:
            self._fetch(level, offset)
        if moved:
            self._changed()

    def _push(self, level):
        """Entra a un nivel; si se carga, primero "Cargando…" y, si el pedido falla, vuelve al anterior."""
        with self._lock:
            if not self._stack:
                return
            self._stack.append(level)
            if level.load is not None:
                level.loading = True
        self._changed()
        if level.load is not None:
            self._fetch(level, 0)

    def _fetch(self, level, offset):
        def job():
            reply = self._request(level.load(offset))
            rows = None
            if reply is not None:
                try:
                    rows, total = level.parse(reply, offset)
                except (KeyError, TypeError, ValueError, AttributeError):
                    rows = None  # respuesta con otra forma
            with self._lock:
                current = bool(self._stack) and self._stack[-1] is level
                level.loading = False
                if current and rows is not None:
                    level.rows.extend(rows)
                    level.fetched += len(rows)
                    level.total = total
                    more = self._next_page(level)  # el cursor pudo llegar al final mientras cargaba
                elif current and offset == 0:
                    self._stack.pop()  # no se pudo entrar: queda donde estaba
                    more = None
                else:
                    more = None
            if not current:
                return  # respuesta de un nivel que ya se dejó
            if rows is None:
                self._toast("Error")
            self._changed()
            if more is not None:
                self._fetch(level, more)
        self._run(job)

    def _act(self, message, *, done):
        """Una acción con respuesta ok: done "close" cierra el menú, "added" da el aviso "Agregado"."""
        def job():
            ok = self._request(message) is not None
            if not ok:
                self._toast("Error")
            elif done == "close":
                self.close()
            else:
                self._toast("Agregado")
        self._run(job)

    def _do(self, action):
        kind, *args = action
        if kind == "browse":
            self._push(self._browse(*args))
        elif kind == "playlists":
            self._push(self._playlists())
        elif kind == "playlist":
            self._push(self._playlist(*args))
        elif kind == "queue":
            self._push(self._queue())
        elif kind == "track_actions":
            uri, title = args
            self._push(_Level(title, [
                _Row("Reproducir", ("play_uri", uri)),
                _Row("Siguiente", ("add", uri, True)),
                _Row("Agregar a la cola", ("add", uri, False)),
            ]))
        elif kind == "playlist_track":
            name, position, title = args
            self._push(_Level(title, [_Row("Reproducir desde aquí", ("play_playlist", name, position))]))
        elif kind == "confirm_off":
            self._push(_Level("¿Apagar?", [_Row("No", ("back",)), _Row("Sí", ("power_off",))]))
        elif kind == "back":
            self.back()
        elif kind == "power_off":
            self.close()
            self._power_off()
        elif kind == "play_uri":
            self._act({"type": "library.play", "uri": args[0]}, done="close")
        elif kind == "add":
            uri, next_ = args
            self._act({"type": "queue.add", "uri": uri, "next": next_}, done="added")
        elif kind == "play_playlist":
            name, position = args
            self._act({"type": "playlist.play", "name": name, "position": position}, done="close")
        elif kind == "queue_play":
            self._act({"type": "queue.play", "position": args[0]}, done="close")

    # Niveles cargados por IPC

    @staticmethod
    def _browse(path):
        def parse(reply, offset):
            rows = []
            for entry in reply["entries"]:
                if entry.get("directory"):
                    rows.append(_Row(_basename(entry["uri"]), ("browse", entry["uri"])))
                else:
                    rows.append(_Row(_label(entry), ("track_actions", entry["uri"], _label(entry))))
            return rows, int(reply["total"])
        fixed = [_Row("▶ Reproducir todo", ("track_actions", path, _basename(path)))] if path else []
        return _Level(_basename(path) if path else "Biblioteca", fixed,
                      lambda offset: {"type": "library.browse", "path": path, "offset": offset}, parse)

    @staticmethod
    def _playlists():
        def parse(reply, offset):
            return [_Row(name, ("playlist", name)) for name in reply["playlists"]], len(reply["playlists"])
        return _Level("Listas", (), lambda offset: {"type": "playlist.list"}, parse)

    @staticmethod
    def _playlist(name):
        def parse(reply, offset):
            rows = [_Row(_label(entry), ("playlist_track", name, offset + i, _label(entry)))
                    for i, entry in enumerate(reply["entries"])]
            return rows, int(reply["total"])
        return _Level(name, [_Row("▶ Reproducir lista", ("play_playlist", name, 0))],
                      lambda offset: {"type": "playlist.get", "name": name, "offset": offset}, parse)

    def _queue(self):
        def parse(reply, offset):
            current = self._queue_position()
            rows = []
            for i, entry in enumerate(reply["entries"]):
                position = offset + i
                label = _label(entry)
                rows.append(_Row(f"♪ {label}" if position == current else label, ("queue_play", position)))
            return rows, int(reply["total"])
        return _Level("Cola", (), lambda offset: {"type": "queue.get", "offset": offset}, parse)
