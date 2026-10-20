import json

import pytest

from conftest import EXAMPLE_CONFIG
from config import BUTTON_NAMES, ConfigError, load_config

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
