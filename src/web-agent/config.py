"""Configuración del web agent: ipc.unixSocketPath y web.port de player.json.

ponytail: duplica la lectura de ipc.unixSocketPath de hardware-agent/config.py para que una sección
hardware inválida no tumbe la web; unificar si aparece un tercer agente.
"""

import json
from dataclasses import dataclass


class ConfigError(Exception):
    """Config inválida; el mensaje nombra el campo."""


@dataclass(frozen=True)
class WebConfig:
    socket_path: str
    port: int


def load_config(path: str) -> WebConfig:
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

    port = _get(data, "web", "port")
    # bool es subclase de int; < 1024 requeriría privilegios.
    if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
        raise ConfigError("web.port must be an integer 1024-65535")

    return WebConfig(socket_path, port)


def _get(data, section: str, key: str):
    value = data.get(section) if isinstance(data, dict) else None
    if not isinstance(value, dict) or key not in value:
        raise ConfigError(f"{section}.{key} is missing")
    return value[key]
