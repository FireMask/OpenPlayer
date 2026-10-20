"""Hardware agent (SPEC 05): botones GPIO → button.pressed por el socket IPC del Service.

Uso: python3 main.py [ruta/player.json]   (por defecto ../player.json, junto al Service en /opt/openplayer)
"""

import logging
import os
import signal
import sys
import threading

from config import ConfigError, load_config
from sender import Sender

log = logging.getLogger("hardware-agent")


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

    sender = Sender(config.socket_path)
    sender.start()
    try:
        # gpiozero se importa aquí: un error de GPIO (paquete, permisos, pin ocupado) sale con 1 y systemd lo ve.
        from buttons import create_buttons
        buttons = create_buttons(config, sender.press)
    except Exception as e:
        log.error("cannot set up GPIO buttons: %s", e)
        sender.stop()
        return 1

    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    log.info("ready: %s", ", ".join(f"{name}=GPIO{pin}" for name, pin in config.pins.items()))

    # wait() con timeout: en Windows un wait sin timeout no deja correr los manejadores de señal.
    while not stopping.wait(1):
        pass
    for button in buttons:
        button.close()
    sender.stop()
    log.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
