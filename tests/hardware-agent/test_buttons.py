import time

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

from buttons import Buttons
from config import AgentConfig
from gestures import Gestures

PINS = {"play_pause": 17, "previous": 27, "next": 22, "volume_up": 23, "volume_down": 24, "menu": 25}
CONFIG = AgentConfig("/x.sock", dict(PINS), 0.08)


def wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met within timeout")


class FakeGestures:
    """Como Gestures, ignora soltar un botón que no estaba apretado (el tick suelta todos los no apretados)."""

    def __init__(self):
        self.events = []  # ("press" | "release", nombre)
        self.ticks = 0
        self._down = set()

    def press(self, name, t):
        self._down.add(name)
        self.events.append(("press", name))

    def release(self, name, t):
        if name in self._down:
            self._down.remove(name)
            self.events.append(("release", name))

    def tick(self, t):
        self.ticks += 1


@pytest.fixture
def factory():
    Device.pin_factory = MockFactory()
    yield Device.pin_factory
    Device.pin_factory.reset()
    Device.pin_factory = None


@pytest.fixture
def make(factory):
    created = []

    def make(gestures, on_press=lambda name: None):
        b = Buttons(CONFIG, gestures, on_press)
        created.append(b)
        return b

    yield make
    for b in created:
        b.close()


def press(factory, pin):
    # Botón entre el pin y GND con pull-up: pulsar = nivel bajo.
    factory.pin(pin).drive_low()
    factory.pin(pin).drive_high()


def test_creates_one_pull_up_button_per_pin(make):
    buttons = make(FakeGestures()).buttons

    assert {str(b.pin) for b in buttons.values()} == {f"GPIO{pin}" for pin in PINS.values()}
    # El debounce lo aplica la capa del pin (lgpio, en el kernel); MockPin lo guarda pero no lo simula.
    assert all(b.pin.bounce == 0.08 for b in buttons.values())
    assert all(b.pull_up for b in buttons.values())


@pytest.mark.parametrize("name, pin", PINS.items())
def test_press_and_release_reach_gestures(factory, make, name, pin):
    gestures, woken = FakeGestures(), []
    make(gestures, woken.append)
    press(factory, pin)

    assert gestures.events == [("press", name), ("release", name)]
    assert woken == [name]


def test_ticks_every_50_ms(make):
    gestures = FakeGestures()
    make(gestures)
    time.sleep(0.3)

    assert 3 <= gestures.ticks <= 7


def test_tick_releases_button_whose_release_event_was_lost(factory, make):
    # Soltar perdido (cable flojo): el tick ve is_pressed en falso y suelta igual.
    gestures = FakeGestures()
    buttons = make(gestures)
    factory.pin(22).drive_low()
    buttons.buttons["next"].when_released = None
    factory.pin(22).drive_high()

    wait_until(lambda: ("release", "next") in gestures.events)


def test_short_press_with_real_gestures_sends_on_release(factory, make):
    sent = []
    make(Gestures(sent.append, lambda text: None, hold=0.6, shutdown_hold=3))
    press(factory, 22)

    assert sent == ["next"]


def test_held_next_seeks_and_never_goes_next(factory, make):
    sent = []
    make(Gestures(sent.append, lambda text: None, hold=0.2, shutdown_hold=3))
    factory.pin(22).drive_low()
    wait_until(lambda: sent)
    factory.pin(22).drive_high()
    time.sleep(0.1)

    assert sent == ["seek_forward"]


def test_held_play_pause_powers_off(factory, make):
    sent = []
    make(Gestures(sent.append, lambda text: None, hold=0.1, shutdown_hold=0.3))
    factory.pin(17).drive_low()
    wait_until(lambda: sent)
    factory.pin(17).drive_high()
    time.sleep(0.1)

    assert sent == ["power_off"]


def test_menu_gestures_never_reach_the_service(factory, make):
    # SPEC 21: menu mantenido abre; con el menú abierto ⏭ y ▶︎ dan nombres locales, no next ni play_pause.
    sent, menu = [], {"open": False}

    def send(name):
        sent.append(name)
        if name == "menu_open":
            menu["open"] = True

    make(Gestures(send, lambda text: None, hold=0.1, shutdown_hold=3, menu_open=lambda: menu["open"]))
    factory.pin(25).drive_low()
    wait_until(lambda: sent)
    factory.pin(25).drive_high()
    press(factory, 22)
    press(factory, 17)
    time.sleep(0.1)

    assert sent == ["menu_open", "menu_down", "menu_select"]
