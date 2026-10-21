import json
import os
import socket
import subprocess
import sys

from conftest import EXAMPLE_CONFIG, ROOT

MAIN = os.path.join(ROOT, "src", "web-agent", "main.py")


def run(config_path, timeout=10):
    return subprocess.run([sys.executable, MAIN, config_path], capture_output=True, text=True, timeout=timeout)


def write_config(tmp_path, change):
    with open(EXAMPLE_CONFIG, encoding="utf-8") as f:
        data = json.load(f)
    change(data)
    path = tmp_path / "player.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_invalid_config_exits_1_naming_field(tmp_path):
    result = run(write_config(tmp_path, lambda d: d["web"].update(port=80)))

    assert result.returncode == 1
    assert "invalid config: web.port" in result.stderr


def test_missing_config_exits_1(tmp_path):
    result = run(str(tmp_path / "nope.json"))

    assert result.returncode == 1
    assert "cannot read" in result.stderr


def test_port_in_use_exits_1(tmp_path):
    busy = socket.socket(socket.AF_INET6)
    busy.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    busy.bind(("::", 0))
    busy.listen()
    port = busy.getsockname()[1]
    try:
        result = run(write_config(tmp_path, lambda d: d["web"].update(port=port)))
    finally:
        busy.close()

    assert result.returncode == 1
    assert f"cannot listen on port {port}" in result.stderr
