"""Write openplayer-buttons.kicad_sch (and .kicad_pro) from netlist.py.

Plain Python; needs KiCad 10 installed for its stock symbol libraries.
Run: python hardware/buttons/scripts/build_sch.py
"""

import sys
from pathlib import Path

BOARD_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOARD_DIR.parent / "common"))
import pcbgen  # noqa: E402
from netlist import NETS, PARTS, pin_net  # noqa: E402

NAME = "openplayer-buttons"

# Sheet position (mm) of each symbol; multiples of 2.54 keep pins on grid. Switches in a column,
# top to bottom like on the board.
POSITIONS = {
    "J1": (101.6, 101.6),
    **{f"SW{i}": (152.4, 50.8 + 15.24 * (i - 1)) for i in range(1, 8)},
    "H1": (203.2, 50.8), "H2": (215.9, 50.8),
}
TEXT_Y = {ref: (y - 5.08, y + 3.81) for ref, (_, y) in POSITIONS.items() if ref.startswith("SW")}  # value close under the switch


def build():
    pcbgen.write_schematic(BOARD_DIR, NAME, "OpenPlayer buttons", "hardware/buttons/scripts/build_sch.py",
                           PARTS, pin_net(), POSITIONS, text_y=TEXT_Y)


if __name__ == "__main__":
    build()
    print(f"wrote {NAME}.kicad_sch ({sum(map(len, NETS.values()))} connected pins)")
