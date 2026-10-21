"""Web agent (SPEC 08): página con los 6 botones → button.pressed / player.get_snapshot por el socket IPC.

Uso: python3 main.py [ruta/player.json]   (por defecto ../player.json, junto al Service en /opt/openplayer)
"""

import logging
import os
import signal
import sys
import threading

from config import ConfigError, load_config
from ipc import Ipc
from server import WebServer

log = logging.getLogger("web-agent")


def main(argv):
    for level in (logging.INFO, logging.WARNING, logging.ERROR):
        logging.addLevelName(level, logging.getLevelName(level).lower())
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s", stream=sys.stderr)

    path = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "player.json")
    try:
        config = load_config(path)
    except ConfigError as e:
        log.error("invalid config: %s", e)
        return 1

    try:
        server = WebServer(config.port, Ipc(config.socket_path))
    except OSError as e:  # puerto ocupado, sin IPv6…: exit 1 para que systemd lo vea
        log.error("cannot listen on port %d: %s", config.port, e)
        return 1

    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    threading.Thread(target=server.serve_forever, name="http", daemon=True).start()
    log.info("ready: http://[::]:%d", config.port)

    # wait() con timeout: en Windows un wait sin timeout no deja correr los manejadores de señal.
    while not stopping.wait(1):
        pass
    server.shutdown()
    server.server_close()
    log.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
