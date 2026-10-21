import json

import pytest

from conftest import EXAMPLE_CONFIG
from config import ConfigError, load_config

DELETE = object()


def example():
    with open(EXAMPLE_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def write(tmp_path, data):
    path = tmp_path / "player.json"
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return str(path)


def mutate(section, key, value):
    def apply(data):
        if value is DELETE:
            del data[section][key]
        else:
            data[section][key] = value
    return apply


def test_loads_example_config():
    config = load_config(EXAMPLE_CONFIG)

    assert config.socket_path == "/run/openplayer/hardware.sock"
    assert config.port == 8080


def test_ignores_invalid_hardware_section(tmp_path):
    data = example()
    data["hardware"] = "broken"

    assert load_config(write(tmp_path, data)).port == 8080


@pytest.mark.parametrize("change, field", [
    (mutate("web", "port", DELETE), "web.port is missing"),
    (mutate("web", "port", 1023), "web.port"),
    (mutate("web", "port", 65536), "web.port"),
    (mutate("web", "port", "8080"), "web.port"),
    (mutate("web", "port", 8080.0), "web.port"),
    (mutate("web", "port", True), "web.port"),
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
    del data["web"]

    with pytest.raises(ConfigError, match=r"web\.port is missing"):
        load_config(write(tmp_path, data))


def test_rejects_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(str(tmp_path / "nope.json"))


def test_rejects_invalid_json(tmp_path):
    with pytest.raises(ConfigError, match="invalid JSON"):
        load_config(write(tmp_path, "{not json"))
