"""Botones GPIO (gpio-map.md): botón entre el pin y GND, pull-up interno y debounce.
SPEC 20: apretar y soltar van a Gestures; un hilo hace tick cada 50 ms."""

import threading
import time

from gpiozero import Button

TICK_SECONDS = 0.05


class Buttons:
    """Un Button por pin, conectados a gestures. on_press(nombre) se llama al apretar y debe volver de inmediato."""

    def __init__(self, config, gestures, on_press=lambda name: None, *, monotonic=time.monotonic):
        self._gestures = gestures
        self._on_press = on_press
        self._monotonic = monotonic
        self._lock = threading.Lock()  # gpiozero y el hilo de tick llaman a Gestures desde hilos distintos
        self.buttons = {}
        for name, pin in config.pins.items():
            button = Button(pin, pull_up=True, bounce_time=config.debounce_seconds)
            button.when_pressed = lambda name=name: self._press(name)
            button.when_released = lambda name=name: self._release(name)
            self.buttons[name] = button
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, name="buttons", daemon=True)
        self._thread.start()

    def close(self):
        self._stopping.set()
        self._thread.join(timeout=5)
        for button in self.buttons.values():
            button.close()

    def _press(self, name):
        self._on_press(name)
        with self._lock:
            self._gestures.press(name, self._monotonic())

    def _release(self, name):
        with self._lock:
            self._gestures.release(name, self._monotonic())

    def _run(self):
        while not self._stopping.wait(TICK_SECONDS):
            with self._lock:
                t = self._monotonic()
                # Por si se pierde el evento de soltar (cable flojo): la repetición se corta con is_pressed.
                for name, button in self.buttons.items():
                    if not button.is_pressed:
                        self._gestures.release(name, t)
                self._gestures.tick(t)
