"""Write openplayer-carrier.kicad_pcb from netlist.py: outline, placement, silkscreen, nets.

Needs KiCad's bundled Python (pcbnew):
  "C:/Program Files/KiCad/10.0/bin/python.exe" hardware/pcb/scripts/build_pcb.py
Positions are relative to BOARD_W / BOARD_H; change them and rerun to resize.
"""

import os
import sys
from pathlib import Path

import pcbnew
from pcbnew import FromMM, VECTOR2I

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_sch import NAME, PCB_DIR, uid  # noqa: E402
from netlist import PARTS, pin_net  # noqa: E402

BOARD_W = 60.0      # mm; the 2×20 header (~56 mm) sets the minimum
BOARD_H = 45.0      # mm
HOLE_INSET = 3.5    # mm from each edge to mounting-hole center
POWER_TRACK = 1.0   # mm, 5V_IN / 5V_SYS / GND
SIGNAL_TRACK = 0.25 # mm, everything else
CLEARANCE = 0.2     # mm (JLCPCB 2-layer default allows 0.127)

ORIGIN = (100.0, 100.0)  # top-left corner of the board in KiCad's page coordinates
FOOTPRINT_DIR = Path(os.environ.get("KICAD10_FOOTPRINT_DIR", r"C:\Program Files\KiCad\10.0\share\kicad\footprints"))

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


def pt(x, y):
    return VECTOR2I(FromMM(ORIGIN[0] + x), FromMM(ORIGIN[1] + y))


def text(board, s, x, y, back, size=1.0, angle=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(pt(x, y))
    t.SetLayer(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    t.SetMirrored(back)
    t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
    t.SetTextThickness(FromMM(size * 0.15))
    t.SetTextAngleDegrees(angle)
    board.Add(t)


def outline(board):
    corners = [(0, 0), (W, 0), (W, H), (0, H)]
    for (x1, y1), (x2, y2) in zip(corners, corners[1:] + corners[:1]):
        seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pt(x1, y1))
        seg.SetEnd(pt(x2, y2))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(FromMM(0.1))
        board.Add(seg)


def place(board, nets):
    owner = pin_net()
    footprints = {}
    for ref, (value, _, fp_id) in PARTS.items():
        lib, name = fp_id.split(":")
        fp = pcbnew.FootprintLoad(str(FOOTPRINT_DIR / f"{lib}.pretty"), name)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetPath(pcbnew.KIID_PATH(f"/{uid('sym', ref)}"))  # links the footprint to its schematic symbol
        fp.SetSheetname("Root")
        fp.SetSheetfile(f"{NAME}.kicad_sch")
        x, y, angle, side = PLACEMENT[ref]
        board.Add(fp)
        if side == "back":
            fp.SetLayerAndFlip(pcbnew.B_Cu)
        fp.SetOrientationDegrees(angle)
        layer = pcbnew.B_CrtYd if side == "back" else pcbnew.F_CrtYd
        center = fp.GetCourtyard(layer).BBox().GetCenter()
        target = pt(x, y)
        fp.Move(VECTOR2I(target.x - center.x, target.y - center.y))
        for pad in fp.Pads():
            n = pad.GetNumber()
            net = owner.get((ref, n), f"unconnected-({ref}-Pin_{n}-Pad{n})" if ref == "J1" else None)
            if net:
                pad.SetNet(nets[net])
        footprints[ref] = fp
    return footprints


def silkscreen(board, footprints):
    def box(ref):
        fp = footprints[ref]
        bb = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
        return [pcbnew.ToMM(v) - o for v, o in
                ((bb.GetLeft(), ORIGIN[0]), (bb.GetTop(), ORIGIN[1]), (bb.GetRight(), ORIGIN[0]), (bb.GetBottom(), ORIGIN[1]))]

    for fp in footprints.values():
        fp.Reference().SetVisible(fp.GetReference().startswith("C"))  # our own labels replace the rest
    for ref in ("J2", "J6", "J3"):  # left column: name to the right
        left, top, right, bottom = box(ref)
        label = f"{ref} {NAMES[ref]}"
        text(board, label, right + 0.6 + len(label) * TEXT * 0.45, (top + bottom) / 2, True, TEXT)
    left, top, right, bottom = box("J4")  # pin labels above the body, name above them
    for pad in footprints["J4"].Pads():
        x = pcbnew.ToMM(pad.GetPosition().x) - ORIGIN[0]
        text(board, PIN_LABELS["J4"][int(pad.GetNumber()) - 1], x, top - 2.2, True, SMALL, angle=90)
    text(board, "J4 BUTTONS", (left + right) / 2, top - 5.2, True, TEXT)
    left, top, right, bottom = box("J5")  # front: pin labels below, name above
    for pad in footprints["J5"].Pads():
        x = pcbnew.ToMM(pad.GetPosition().x) - ORIGIN[0]
        text(board, PIN_LABELS["J5"][int(pad.GetNumber()) - 1], x, bottom + 2.2, False, SMALL, angle=90)
    text(board, "J5 DISPLAY", (left + right) / 2, top - 1.0, False, TEXT)
    for ref in ("TP1", "TP2", "TP3"):
        left, top, right, bottom = box(ref)
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
    outline(board)
    footprints = place(board, nets)
    silkscreen(board, footprints)
    unused = [n for n, item in nets.items() if item.GetNetCode() and not any(
        p.GetNetname() == item.GetNetname() for fp in footprints.values() for p in fp.Pads())]
    for n in unused:
        board.Remove(nets[n])
    path = PCB_DIR / f"{NAME}.kicad_pcb"
    pcbnew.SaveBoard(str(path), board)
    return path


if __name__ == "__main__":
    print(f"wrote {build().name} ({BOARD_W} x {BOARD_H} mm)")
