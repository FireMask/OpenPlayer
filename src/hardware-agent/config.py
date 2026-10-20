"""Configuración del agente: secciones hardware e ipc de player.json (architecture.md §10)."""

import json
from dataclasses import dataclass

BUTTON_NAMES = ("play_pause", "previous", "next", "volume_up", "volume_down", "menu")


class ConfigError(Exception):
    """Config inválida; el mensaje nombra el campo."""


@dataclass(frozen=True)
class AgentConfig:
    socket_path: str
    pins: dict  # nombre IPC → pin BCM
    debounce_seconds: float


def load_config(path: str) -> AgentConfig:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise ConfigError(f"cannot read {path}: {e.strerror}") from e
    except json.JSONDecodeError as e:
        raise ConfigError(f"invalid JSON in {path}: {e}") from e

    socket_path = _get(data, "ipc", "unixSocketPath")
    if not isinstance(socket_path, str) or not socket_path.strip():
        raise ConfigError("ipc.unixSocketPath must be a non-empty string")

    buttons = _get(data, "hardware", "buttons")
    if not isinstance(buttons, dict) or set(buttons) != set(BUTTON_NAMES):
        raise ConfigError(f"hardware.buttons must have exactly: {', '.join(BUTTON_NAMES)}")
    pins = {}
    for name in BUTTON_NAMES:
        pin = buttons[name]
        # bool es subclase de int: true/false no son pines.
        if not isinstance(pin, int) or isinstance(pin, bool) or not 0 <= pin <= 27:
            raise ConfigError(f"hardware.buttons.{name} must be a BCM pin 0-27")
        if pin in pins.values():
            raise ConfigError(f"hardware.buttons.{name}: pin {pin} is already used")
        pins[name] = pin

    debounce = _get(data, "hardware", "debounceSeconds")
    if not isinstance(debounce, (int, float)) or isinstance(debounce, bool) or not 0.01 <= debounce <= 1:
        raise ConfigError("hardware.debounceSeconds must be 0.01-1")

    return AgentConfig(socket_path, pins, float(debounce))


def _get(data, section: str, key: str):
    value = data.get(section) if isinstance(data, dict) else None
    if not isinstance(value, dict) or key not in value:
        raise ConfigError(f"{section}.{key} is missing")
    return value[key]
