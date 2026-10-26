"""Write openplayer-carrier.kicad_sch (and .kicad_pro) from netlist.py.

Plain Python; needs KiCad 10 installed for its stock symbol libraries.
Every pin gets a net label at its tip; unused J1 pins get a no-connect flag.
Run: python hardware/pcb/scripts/build_sch.py
"""

import sys
from pathlib import Path

PCB_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PCB_DIR.parent / "common"))
import pcbgen  # noqa: E402
from netlist import NETS, PARTS, pin_net  # noqa: E402

NAME = "openplayer-carrier"

# Sheet position (mm) of each symbol; multiples of 2.54 keep pins on grid.
POSITIONS = {
    "J1": (101.6, 101.6),
    "J2": (172.72, 50.8), "J6": (172.72, 66.04), "J3": (172.72, 81.28),
    "J4": (172.72, 101.6), "J5": (172.72, 132.08),
    "C1": (213.36, 50.8), "C2": (233.68, 50.8),
    "TP1": (213.36, 81.28), "TP2": (226.06, 81.28), "TP3": (238.76, 81.28),
    "H1": (213.36, 109.22), "H2": (226.06, 109.22), "H3": (238.76, 109.22), "H4": (251.46, 109.22),
}


def build():
    pcbgen.write_schematic(PCB_DIR, NAME, "OpenPlayer carrier", "hardware/pcb/scripts/build_sch.py",
                           PARTS, pin_net(), POSITIONS, text_y={"J1": (101.6 - 30.48, 101.6 + 30.48)})


if __name__ == "__main__":
    build()
    print(f"wrote {NAME}.kicad_sch ({sum(map(len, NETS.values()))} connected pins)")
