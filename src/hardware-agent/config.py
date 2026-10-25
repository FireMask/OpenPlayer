"""Configuración del agente: secciones hardware e ipc de player.json (architecture.md §10)."""

import json
import re
from dataclasses import dataclass
from datetime import time

BUTTON_NAMES = ("play_pause", "previous", "next", "volume_up", "volume_down", "menu")


class ConfigError(Exception):
    """Config inválida; el mensaje nombra el campo."""


@dataclass(frozen=True)
class DisplayConfig:
    """Pantalla GC9A01 por SPI (SPEC 17)."""
    spi_bus: int
    spi_device: int
    dc: int  # BCM
    rst: int  # BCM
    spi_hz: int
    rotation: int  # 0 | 90 | 180 | 270
    # SPEC 18: None desactiva cada uno.
    idle_clock_seconds: int | None = 60
    night: tuple[time, time] | None = None  # (inicio, fin); puede cruzar la medianoche
    off_after_stopped_minutes: int | None = None


@dataclass(frozen=True)
class AgentConfig:
    socket_path: str
    pins: dict  # nombre IPC → pin BCM
    debounce_seconds: float
    display: DisplayConfig | None = None  # None: sección ausente o enabled=false


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

    return AgentConfig(socket_path, pins, float(debounce), _display(data["hardware"], pins))


def _display(hardware: dict, pins: dict) -> DisplayConfig | None:
    section = hardware.get("display")
    if section is None:
        return None
    if not isinstance(section, dict):
        raise ConfigError("hardware.display must be an object")
    enabled = section.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("hardware.display.enabled must be true or false")
    if not enabled:
        return None

    def field(key, valid, rule):
        if key not in section:
            raise ConfigError(f"hardware.display.{key} is missing")
        value = section[key]
        if not isinstance(value, int) or isinstance(value, bool) or not valid(value):
            raise ConfigError(f"hardware.display.{key} must be {rule}")
        return value

    bus = field("spiBus", lambda v: 0 <= v <= 1, "0-1")
    device = field("spiDevice", lambda v: 0 <= v <= 1, "0-1")
    used = dict(pins)
    gpio = {}
    for key in ("dc", "rst"):
        pin = field(key, lambda v: 0 <= v <= 27, "a BCM pin 0-27")
        if pin in used.values():
            raise ConfigError(f"hardware.display.{key}: pin {pin} is already used")
        used[key] = gpio[key] = pin
    hz = field("spiHz", lambda v: 1_000_000 <= v <= 62_500_000, "1000000-62500000")
    rotation = field("rotation", lambda v: v in (0, 90, 180, 270), "0, 90, 180 or 270")

    # SPEC 18: opcionales; ausente = defecto, null = desactivado.
    def optional(key, default, low, high):
        value = section.get(key, default)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high):
            raise ConfigError(f"hardware.display.{key} must be {low}-{high} or null")
        return value

    idle = optional("idleClockSeconds", 60, 1, 3600)
    off = optional("offAfterStoppedMinutes", None, 1, 1440)
    start, end = (_clock_time(section, key) for key in ("nightStart", "nightEnd"))
    if (start is None) != (end is None):
        raise ConfigError("hardware.display.nightStart and nightEnd must both be set or both be null")
    if start is not None and start == end:
        raise ConfigError("hardware.display.nightStart and nightEnd must differ")
    night = (start, end) if start is not None else None
    return DisplayConfig(bus, device, gpio["dc"], gpio["rst"], hz, rotation, idle, night, off)


def _clock_time(section: dict, key: str) -> time | None:
    value = section.get(key)
    if value is None:
        return None
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", value) if isinstance(value, str) else None
    if not match:
        raise ConfigError(f"hardware.display.{key} must be HH:MM or null")
    return time(int(match[1]), int(match[2]))


def _get(data, section: str, key: str):
    value = data.get(section) if isinstance(data, dict) else None
    if not isinstance(value, dict) or key not in value:
        raise ConfigError(f"{section}.{key} is missing")
    return value[key]
