"""Hardware agent (SPEC 05): botones GPIO → button.pressed por el socket IPC del Service.
Con hardware.display habilitada (SPEC 17), también dibuja la pista actual en la pantalla GC9A01.

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
    display = None

    def press(name):
        if display:
            display.wake()  # SPEC 18: cualquier botón enciende la pantalla apagada, y además hace su acción
        sender.press(name)

    try:
        # gpiozero se importa aquí: un error de GPIO (paquete, permisos, pin ocupado) sale con 1 y systemd lo ve.
        from buttons import create_buttons
        buttons = create_buttons(config, press)
    except Exception as e:
        log.error("cannot set up GPIO buttons: %s", e)
        sender.stop()
        return 1

    display = _start_display(config) if config.display else None

    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    log.info("ready: %s", ", ".join(f"{name}=GPIO{pin}" for name, pin in config.pins.items()))

    # wait() con timeout: en Windows un wait sin timeout no deja correr los manejadores de señal.
    while not stopping.wait(1):
        pass
    if display:
        display.stop()
        display.panel.close()
    for button in buttons:
        button.close()
    sender.stop()
    log.info("stopped")
    return 0


def _start_display(config):
    """Arma y arranca la pantalla. Cualquier error (paquete, SPI, pin) se registra y los botones siguen."""
    d = config.display
    opened = []
    try:
        # Importados aquí: sin pantalla, el agente no necesita spidev ni Pillow.
        import spidev
        from gpiozero import DigitalOutputDevice

        from display import Display
        from gc9a01 import GC9A01

        dc = DigitalOutputDevice(d.dc)
        opened.append(dc)
        rst = DigitalOutputDevice(d.rst)
        opened.append(rst)
        spi = spidev.SpiDev()
        spi.open(d.spi_bus, d.spi_device)
        opened.append(spi)
        panel = GC9A01(spi, dc, rst, spi_hz=d.spi_hz, rotation=d.rotation)
        display = Display(config.socket_path, panel, label=f"spi{d.spi_bus}.{d.spi_device}, {d.spi_hz} Hz",
                          idle_clock_seconds=d.idle_clock_seconds, night=d.night,
                          off_after_stopped_minutes=d.off_after_stopped_minutes)
    except Exception as e:
        log.error("display init failed: %s", e)
        for resource in opened:
            resource.close()
        return None
    display.start()
    return display


if __name__ == "__main__":
    sys.exit(main(sys.argv))
