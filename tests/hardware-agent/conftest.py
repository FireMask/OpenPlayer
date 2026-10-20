import os
import sys

# El agente no es un paquete instalable: sus módulos se importan desde src/hardware-agent.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src", "hardware-agent"))

EXAMPLE_CONFIG = os.path.join(ROOT, "config", "player.example.json")
