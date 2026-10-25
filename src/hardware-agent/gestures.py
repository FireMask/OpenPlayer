"""Gestos de los botones (SPEC 20): pulsación corta, mantenida y apagado manteniendo ▶︎.

Máquina de estados pura, sin GPIO ni hilos: el tiempo lo pasa quien llama (time.monotonic() en buttons.py).
Una pulsación larga nunca dispara la acción corta.
"""

import math

SEEK = {"next": ("seek_forward", "+10 s"), "previous": ("seek_backward", "−10 s")}
VOLUME = ("volume_up", "volume_down")
MENU_TOAST = "Menú: próximamente"


class _Press:
    def __init__(self, start):
        self.start = start
        self.held = False  # ya pasó a mantenida
        self.next = None  # próxima repetición (seek/volumen)
        self.shown = None  # último número de la cuenta de apagado
        self.done = False  # power_off ya enviado


class Gestures:
    def __init__(self, send, toast, *, hold, shutdown_hold, seek_repeat=0.5, volume_repeat=0.25):
        self._send = send
        self._toast = toast
        self._hold = hold
        self._shutdown_hold = shutdown_hold
        self._seek_repeat = seek_repeat
        self._volume_repeat = volume_repeat
        self._down = {}  # nombre → _Press; uno por botón, independientes

    def press(self, name, t):
        if name in self._down:
            return  # rebote: ya estaba apretado
        self._down[name] = _Press(t)
        if name in VOLUME:
            self._send(name)  # vol±: al apretar, como antes de SPEC 20

    def release(self, name, t):
        state = self._down.get(name)
        if state is None:
            return
        self._advance(name, state, t)  # un tick atrasado no convierte una larga en corta
        del self._down[name]
        if not state.held:
            if name not in VOLUME:
                self._send(name)
        elif name == "play_pause" and not state.done:
            self._toast(None)  # cuenta cancelada

    def tick(self, t):
        for name, state in list(self._down.items()):
            self._advance(name, state, t)

    def _advance(self, name, state, t):
        elapsed = t - state.start
        if name == "play_pause":
            self._shutdown(state, elapsed)
            return
        if not state.held:
            if elapsed < self._hold:
                return
            state.held = True
            if name == "menu":
                self._toast(MENU_TOAST)
                return
            state.next = t  # la primera repetición sale enseguida
        if name == "menu" or t < state.next:
            return
        if name in SEEK:
            command, text = SEEK[name]
            self._send(command)
            self._toast(text)
            repeat = self._seek_repeat
        else:
            self._send(name)
            repeat = self._volume_repeat
        # Sin ráfagas si un tick llega tarde.
        state.next = state.next + repeat if state.next + repeat > t else t + repeat

    def _shutdown(self, state, elapsed):
        if state.done:
            return
        if elapsed >= self._shutdown_hold:
            state.held = state.done = True
            self._send("power_off")
            return
        if elapsed < self._hold:
            return
        state.held = True
        remaining = math.ceil(self._shutdown_hold - elapsed)
        if remaining != state.shown:
            state.shown = remaining
            self._toast(f"Apagar {remaining}…")
