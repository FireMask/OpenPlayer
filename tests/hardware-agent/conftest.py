import os
import sys

# El agente no es un paquete instalable: sus módulos se importan desde src/hardware-agent.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src", "hardware-agent"))

EXAMPLE_CONFIG = os.path.join(ROOT, "config", "player.example.json")

# screen.py usa la ruta de fonts-dejavu-core de la Pi; en Windows, la copia de DejaVu del sistema.
WINDOWS_FONT = r"C:\Windows\Fonts\DejaVuSans.ttf"
try:
    import screen
except ImportError:  # Pillow no instalado: solo fallan las pruebas que lo usan.
    pass
else:
    if not os.path.exists(screen.FONT_PATH) and os.path.exists(WINDOWS_FONT):
        screen.FONT_PATH = WINDOWS_FONT
