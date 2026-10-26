"""Hardware agent (SPEC 05): botones GPIO → button.pressed por el socket IPC del Service.
Con hardware.display habilitada (SPEC 17), también dibuja la pista actual en la pantalla GC9A01,
y menu mantenido abre el menú en pantalla (SPEC 21).

Uso: python3 main.py [ruta/player.json]   (por defecto ../player.json, junto al Service en /opt/openplayer)
"""

import logging
import os
import signal
import sys
import threading

from config import ConfigError, load_config
from gestures import Gestures
from sender import Sender, connect_unix, request

log = logging.getLogger("hardware-agent")

MENU_ACTIONS = {"menu_open": "open", "menu_close": "close", "menu_up": "up", "menu_down": "down",
                "menu_select": "select", "menu_back": "back"}


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
    menu = None  # solo con pantalla (SPEC 21)

    def wake(name):
        if display:
            display.wake()  # SPEC 18: cualquier botón enciende la pantalla apagada, y además hace su acción

    def send(name):
        if name.startswith("menu_"):
            if menu:
                getattr(menu, MENU_ACTIONS[name])()  # nombres locales de gestures.py: no van al Service
            return
        sender.press(name)
        if name == "power_off" and display:
            display.shutting_down()

    def toast(text):
        if display:
            display.toast(text)

    gestures = Gestures(send, toast, hold=config.hold_seconds, shutdown_hold=config.shutdown_hold_seconds,
                        menu_open=lambda: menu is not None and menu.is_open)
    try:
        # gpiozero se importa aquí: un error de GPIO (paquete, permisos, pin ocupado) sale con 1 y systemd lo ve.
        from buttons import Buttons
        buttons = Buttons(config, gestures, wake)
    except Exception as e:
        log.error("cannot set up GPIO buttons: %s", e)
        sender.stop()
        return 1

    if config.display:
        display, menu = _start_display(config, send, toast)

    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    log.info("ready: %s", ", ".join(f"{name}=GPIO{pin}" for name, pin in config.pins.items()))

    # wait() con timeout: en Windows un wait sin timeout no deja correr los manejadores de señal.
    while not stopping.wait(1):
        pass
    buttons.close()  # antes que la pantalla: ningún aviso dibuja sobre el panel cerrado
    if display:
        display.stop()
        _sleep_panel(display.panel)
        display.panel.close()
    sender.stop()
    log.info("stopped")
    return 0


def _sleep_panel(panel):
    """DISPOFF (SPEC 20): tras poweroff el panel sigue alimentado y mostraría "Apagando…" para siempre."""
    try:
        panel.sleep_display()
    except Exception as e:
        log.warning("display off failed: %s", e)


def _start_display(config, send, toast):
    """Arma y arranca la pantalla y su menú (SPEC 21); (None, None) si algo falla (paquete, SPI, pin),
    que se registra, y los botones siguen."""
    d = config.display
    opened = []
    try:
        # Importados aquí: sin pantalla, el agente no necesita spidev ni Pillow.
        import spidev
        from gpiozero import DigitalOutputDevice

        from display import Display
        from gc9a01 import GC9A01
        from menu import Menu

        dc = DigitalOutputDevice(d.dc)
        opened.append(dc)
        rst = DigitalOutputDevice(d.rst)
        opened.append(rst)
        spi = spidev.SpiDev()
        spi.open(d.spi_bus, d.spi_device)
        opened.append(spi)
        panel = GC9A01(spi, dc, rst, spi_hz=d.spi_hz, rotation=d.rotation)
        # changed y queue_position, por lambda: display todavía no existe (y el menú no se usa hasta el return).
        menu = Menu(lambda message: request(lambda: connect_unix(config.socket_path), message),
                    power_off=lambda: send("power_off"), toast=toast, changed=lambda: display.refresh(),
                    queue_position=lambda: display.queue_position())
        display = Display(config.socket_path, panel, label=f"spi{d.spi_bus}.{d.spi_device}, {d.spi_hz} Hz",
                          idle_clock_seconds=d.idle_clock_seconds, night=d.night,
                          off_after_stopped_minutes=d.off_after_stopped_minutes, menu=menu)
    except Exception as e:
        log.error("display init failed: %s", e)
        for resource in opened:
            resource.close()
        return None, None
    display.start()
    return display, menu


if __name__ == "__main__":
    sys.exit(main(sys.argv))
