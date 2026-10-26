"""Write openplayer-carrier.kicad_pcb from netlist.py: outline, placement, silkscreen, nets, routing.

Needs KiCad's bundled Python (pcbnew):
  "C:/Program Files/KiCad/10.0/bin/python.exe" hardware/pcb/scripts/build_pcb.py
Positions are relative to BOARD_W / BOARD_H; change them and rerun to resize.
"""

import sys
from pathlib import Path

import pcbnew
from pcbnew import FromMM

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_sch import NAME, PCB_DIR  # noqa: E402  (also puts hardware/common on sys.path)
import pcbgen  # noqa: E402
from netlist import PARTS, pin_net  # noqa: E402
from pcbgen import box, text  # noqa: E402

BOARD_W = 60.0      # mm; the 2×20 header (~56 mm) sets the minimum
BOARD_H = 45.0      # mm
HOLE_INSET = 3.5    # mm from each edge to mounting-hole center
POWER_TRACK = 1.0   # mm, 5V_IN / 5V_SYS / GND
SIGNAL_TRACK = 0.25 # mm, everything else
POWER_NETS = {"5V_IN", "5V_SYS"}
ROUTE_ORDER = ["5V_IN", "5V_SYS", "3V3", "SPI_SCLK", "SPI_MOSI", "LCD_CS", "LCD_DC", "LCD_RST",
               "BTN_PLAY", "BTN_PREV", "BTN_NEXT", "BTN_VOLUP", "BTN_VOLDN", "BTN_MENU", "PWR_KEY"]

W, H = BOARD_W, BOARD_H
# ref → (courtyard center x, y in mm from the board's top-left, rotation°, side).
# Left parts anchor to the left edge, right parts to the right edge, J1/J5 to the center.
PLACEMENT = {
    "J5": (W / 2, 4.5, 90, "front"),          # display header; the module hangs over the board
    "J1": (W / 2, H - 12, 270, "back"),       # Pi ribbon, full width above the bottom holes; pin 1 left
    "J2": (8, 9.6, 0, "back"),                # power entry, left column
    "J6": (8, 16.6, 0, "back"),
    "J3": (8, 23.6, 0, "back"),
    "C1": (25.25, 12.25, 0, "back"),
    "C2": (24, H - 22.5, 0, "back"),          # next to J1 pins 2/4
    "J4": (W - 16.25, H - 21, 0, "back"),     # buttons
    "TP1": (W - 20, 9, 0, "back"),
    "TP2": (W - 15.5, 9, 0, "back"),
    "TP3": (W - 11, 9, 0, "back"),
    "H1": (HOLE_INSET, HOLE_INSET, 0, "front"),
    "H2": (W - HOLE_INSET, HOLE_INSET, 0, "front"),
    "H3": (HOLE_INSET, H - HOLE_INSET, 0, "front"),
    "H4": (W - HOLE_INSET, H - HOLE_INSET, 0, "front"),
}
NAMES = {"J1": "PI", "J2": "PWR_IN", "J3": "KEY", "J4": "BUTTONS", "J5": "DISPLAY", "J6": "SWITCH",
         "TP1": "GND", "TP2": "5V", "TP3": "3V3"}
PIN_LABELS = {
    "J4": ["GND", "PLAY", "PREV", "NEXT", "VOL+", "VOL-", "MENU", "KEY"],
    "J5": ["VCC", "GND", "SCL", "SDA", "DC", "CS", "RST"],
}
TEXT = 0.9   # mm, connector names
SMALL = 0.8  # mm, pin labels; JLCPCB / KiCad minimum


def silkscreen(board, footprints):
    for fp in footprints.values():
        fp.Reference().SetVisible(fp.GetReference().startswith("C"))  # our own labels replace the rest
    for ref in ("J2", "J6", "J3"):  # left column: name to the right
        left, top, right, bottom = box(footprints[ref])
        label = f"{ref} {NAMES[ref]}"
        text(board, label, right + 0.6 + len(label) * TEXT * 0.45, (top + bottom) / 2, True, TEXT)
    left, top, right, bottom = box(footprints["J4"])  # pin labels above the body, name above them
    for pad in footprints["J4"].Pads():
        x = pcbnew.ToMM(pad.GetPosition().x) - pcbgen.ORIGIN[0]
        text(board, PIN_LABELS["J4"][int(pad.GetNumber()) - 1], x, top - 2.2, True, SMALL, angle=90)
    text(board, "J4 BUTTONS", (left + right) / 2, top - 5.2, True, TEXT)
    left, top, right, bottom = box(footprints["J5"])  # front: pin labels below, name above
    for pad in footprints["J5"].Pads():
        x = pcbnew.ToMM(pad.GetPosition().x) - pcbgen.ORIGIN[0]
        text(board, PIN_LABELS["J5"][int(pad.GetNumber()) - 1], x, bottom + 2.2, False, SMALL, angle=90)
    text(board, "J5 DISPLAY", (left + right) / 2, top - 1.0, False, TEXT)
    for ref in ("TP1", "TP2", "TP3"):
        left, top, right, bottom = box(footprints[ref])
        text(board, NAMES[ref], (left + right) / 2, bottom + 0.8, True, SMALL)
    text(board, "J1 PI  (pin 1 ▸)", 13, H - 5.4, True, TEXT)
    text(board, "OpenPlayer carrier Rev A", W / 2 + 6, H - 5.4, True, 1.0)
    text(board, "DO NOT USE PI MICRO-USB POWER WHILE CONNECTED", W / 2, H - 3.2, True, SMALL)
    text(board, "OpenPlayer Rev A", W / 2, H - 3.2, False, 1.0)


def build():
    board = pcbnew.CreateEmptyBoard()
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    nets = {}
    for name in list(pin_net().values()) + [f"unconnected-(J1-Pin_{n}-Pad{n})" for n in range(1, 41)]:
        if name not in nets:
            nets[name] = pcbnew.NETINFO_ITEM(board, name if name.startswith("unconnected") else f"/{name}")  # local labels → /NAME
            board.Add(nets[name])
    pcbgen.outline(board, W, H)
    footprints = pcbgen.place(board, nets, NAME, PARTS, pin_net(), PLACEMENT,
                              lambda ref, n: f"unconnected-({ref}-Pin_{n}-Pad{n})" if ref == "J1" else None)
    silkscreen(board, footprints)
    ds.m_CopperEdgeClearance = FromMM(pcbgen.EDGE_CLEARANCE)
    router = pcbgen.Router(footprints, W, H, ("J1", "1"), SIGNAL_TRACK, POWER_TRACK, POWER_NETS)
    for net in ROUTE_ORDER:
        router.route_net(board, net, nets[net])
    pcbgen.pour(board, nets["GND"], router.stitch(board, nets["GND"]), W, H)
    path = PCB_DIR / f"{NAME}.kicad_pcb"
    pcbgen.save(board, nets, footprints, path)
    return path


if __name__ == "__main__":
    print(f"wrote {build().name} ({BOARD_W} x {BOARD_H} mm)")
