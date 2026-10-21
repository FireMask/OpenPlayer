import time

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

from buttons import create_buttons
from config import AgentConfig

PINS = {"play_pause": 17, "previous": 27, "next": 22, "volume_up": 23, "volume_down": 24, "menu": 25}


@pytest.fixture
def factory():
    Device.pin_factory = MockFactory()
    yield Device.pin_factory
    Device.pin_factory.reset()
    Device.pin_factory = None


@pytest.fixture
def pressed(factory):
    events = []
    buttons = create_buttons(AgentConfig("/x.sock", dict(PINS), 0.08), events.append)
    yield events
    for button in buttons:
        button.close()


def press(factory, pin):
    # Botón entre el pin y GND con pull-up: pulsar = nivel bajo.
    factory.pin(pin).drive_low()
    factory.pin(pin).drive_high()


def test_creates_one_pull_up_button_per_pin(factory):
    buttons = create_buttons(AgentConfig("/x.sock", dict(PINS), 0.08), lambda name: None)

    assert {str(b.pin) for b in buttons} == {f"GPIO{pin}" for pin in PINS.values()}
    # El debounce lo aplica la capa del pin (lgpio, en el kernel); MockPin lo guarda pero no lo simula.
    assert all(b.pin.bounce == 0.08 for b in buttons)
    assert all(b.pull_up for b in buttons)
    for button in buttons:
        button.close()


@pytest.mark.parametrize("name, pin", PINS.items())
def test_press_reports_button_name(factory, pressed, name, pin):
    press(factory, pin)

    assert pressed == [name]


def test_press_after_debounce_is_a_new_event(factory, pressed):
    press(factory, 22)
    time.sleep(0.15)
    press(factory, 22)

    assert pressed == ["next", "next"]
