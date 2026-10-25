import json
from datetime import time

import pytest

from conftest import EXAMPLE_CONFIG
from config import BUTTON_NAMES, ConfigError, DisplayConfig, load_config

DELETE = object()


def example():
    with open(EXAMPLE_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def write(tmp_path, data):
    path = tmp_path / "player.json"
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return str(path)


def test_loads_example_config():
    config = load_config(EXAMPLE_CONFIG)

    assert config.socket_path == "/run/openplayer/hardware.sock"
    assert config.pins == {"play_pause": 17, "previous": 27, "next": 22,
                           "volume_up": 23, "volume_down": 24, "menu": 25}
    assert config.debounce_seconds == 0.08


def test_accepts_integer_debounce(tmp_path):
    data = example()
    data["hardware"]["debounceSeconds"] = 1

    assert load_config(write(tmp_path, data)).debounce_seconds == 1.0


def mutate(section, key, value):
    def apply(data):
        if value is DELETE:
            del data[section][key]
        else:
            data[section][key] = value
    return apply


def set_pin(name, value):
    def apply(data):
        if value is DELETE:
            del data["hardware"]["buttons"][name]
        else:
            data["hardware"]["buttons"][name] = value
    return apply


@pytest.mark.parametrize("change, field", [
    (set_pin("menu", DELETE), "hardware.buttons"),
    (set_pin("shutdown", 5), "hardware.buttons"),
    (set_pin("next", 28), "hardware.buttons.next"),
    (set_pin("next", -1), "hardware.buttons.next"),
    (set_pin("next", "22"), "hardware.buttons.next"),
    (set_pin("next", 22.0), "hardware.buttons.next"),
    (set_pin("next", True), "hardware.buttons.next"),
    (set_pin("next", 17), "hardware.buttons.next: pin 17 is already used"),
    (mutate("hardware", "buttons", [17, 27]), "hardware.buttons"),
    (mutate("hardware", "debounceSeconds", 0.001), "hardware.debounceSeconds"),
    (mutate("hardware", "debounceSeconds", 2), "hardware.debounceSeconds"),
    (mutate("hardware", "debounceSeconds", "0.08"), "hardware.debounceSeconds"),
    (mutate("hardware", "debounceSeconds", DELETE), "hardware.debounceSeconds is missing"),
    (mutate("ipc", "unixSocketPath", ""), "ipc.unixSocketPath"),
    (mutate("ipc", "unixSocketPath", "  "), "ipc.unixSocketPath"),
    (mutate("ipc", "unixSocketPath", DELETE), "ipc.unixSocketPath is missing"),
])
def test_rejects_invalid_config(tmp_path, change, field):
    data = example()
    change(data)

    with pytest.raises(ConfigError, match=field.replace(".", r"\.")):
        load_config(write(tmp_path, data))


def test_rejects_missing_section(tmp_path):
    data = example()
    del data["hardware"]

    with pytest.raises(ConfigError, match=r"hardware\.buttons is missing"):
        load_config(write(tmp_path, data))


def test_rejects_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(str(tmp_path / "nope.json"))


@pytest.mark.parametrize("text", ["{", "[]", ""])
def test_rejects_invalid_json(tmp_path, text):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, text))


def test_button_names_match_ipc_contract():
    assert BUTTON_NAMES == ("play_pause", "previous", "next", "volume_up", "volume_down", "menu")


# hardware.display (SPEC 17)

def with_display(**fields):
    data = example()
    data["hardware"]["display"].update({"enabled": True, **fields})
    return data


def test_example_display_is_disabled():
    assert load_config(EXAMPLE_CONFIG).display is None


def test_missing_display_section_is_none(tmp_path):
    data = example()
    del data["hardware"]["display"]

    assert load_config(write(tmp_path, data)).display is None


def test_loads_enabled_display(tmp_path):
    display = load_config(write(tmp_path, with_display())).display

    assert display == DisplayConfig(spi_bus=0, spi_device=0, dc=16, rst=26, spi_hz=40_000_000, rotation=180)


@pytest.mark.parametrize("fields, field", [
    ({"spiBus": 2}, "hardware.display.spiBus"),
    ({"spiDevice": -1}, "hardware.display.spiDevice"),
    ({"dc": 28}, "hardware.display.dc"),
    ({"dc": "5"}, "hardware.display.dc"),
    ({"rst": True}, "hardware.display.rst"),
    ({"rst": 16}, "hardware.display.rst: pin 16 is already used"),
    ({"dc": 17}, "hardware.display.dc: pin 17 is already used"),
    ({"spiHz": 999_999}, "hardware.display.spiHz"),
    ({"spiHz": 62_500_001}, "hardware.display.spiHz"),
    ({"rotation": 45}, "hardware.display.rotation"),
    ({"enabled": "yes"}, "hardware.display.enabled"),
])
def test_rejects_invalid_display(tmp_path, fields, field):
    with pytest.raises(ConfigError, match=field.replace(".", r"\.")):
        load_config(write(tmp_path, with_display(**fields)))


def test_rejects_missing_display_field(tmp_path):
    data = with_display()
    del data["hardware"]["display"]["rst"]

    with pytest.raises(ConfigError, match=r"hardware\.display\.rst is missing"):
        load_config(write(tmp_path, data))


def test_rejects_display_not_object(tmp_path):
    data = example()
    data["hardware"]["display"] = True

    with pytest.raises(ConfigError, match=r"hardware\.display must be an object"):
        load_config(write(tmp_path, data))


# Campos opcionales de la pantalla (SPEC 18)

def test_display_without_new_fields_uses_defaults(tmp_path):
    data = with_display()
    for key in ("idleClockSeconds", "nightStart", "nightEnd", "offAfterStoppedMinutes"):
        del data["hardware"]["display"][key]
    display = load_config(write(tmp_path, data)).display

    assert (display.idle_clock_seconds, display.night, display.off_after_stopped_minutes) == (60, None, None)


def test_loads_display_power_fields(tmp_path):
    data = with_display(idleClockSeconds=None, nightStart="23:00", nightEnd="07:30", offAfterStoppedMinutes=15)
    display = load_config(write(tmp_path, data)).display

    assert display.idle_clock_seconds is None
    assert display.night == (time(23, 0), time(7, 30))
    assert display.off_after_stopped_minutes == 15


@pytest.mark.parametrize("fields, field", [
    ({"idleClockSeconds": 0}, "hardware.display.idleClockSeconds"),
    ({"idleClockSeconds": 3601}, "hardware.display.idleClockSeconds"),
    ({"idleClockSeconds": True}, "hardware.display.idleClockSeconds"),
    ({"offAfterStoppedMinutes": 0}, "hardware.display.offAfterStoppedMinutes"),
    ({"offAfterStoppedMinutes": 1441}, "hardware.display.offAfterStoppedMinutes"),
    ({"nightStart": "23:00"}, "hardware.display.nightStart and nightEnd must both be set"),
    ({"nightEnd": "07:00"}, "hardware.display.nightStart and nightEnd must both be set"),
    ({"nightStart": "24:00", "nightEnd": "07:00"}, "hardware.display.nightStart must be HH:MM"),
    ({"nightStart": "23:00", "nightEnd": "7:00"}, "hardware.display.nightEnd must be HH:MM"),
    ({"nightStart": 2300, "nightEnd": "07:00"}, "hardware.display.nightStart must be HH:MM"),
    ({"nightStart": "07:00", "nightEnd": "07:00"}, "hardware.display.nightStart and nightEnd must differ"),
])
def test_rejects_invalid_display_power_fields(tmp_path, fields, field):
    with pytest.raises(ConfigError, match=field.replace(".", r"\.")):
        load_config(write(tmp_path, with_display(**fields)))
