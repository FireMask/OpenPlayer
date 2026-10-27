"""Write openplayer-carrier.kicad_pcb from netlist.py: outline, placement, silkscreen, nets, routing.

Needs KiCad's bundled Python (pcbnew):
  "C:/Program Files/KiCad/10.0/bin/python.exe" hardware/pcb/scripts/build_pcb.py
Positions are relative to BOARD_W / BOARD_H; change them and rerun to resize.
Rev B (SPEC 24): single-sided (all parts on the back), every connector's mouth at a board edge.
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

BOARD_W = 60.0      # mm; J1's 2×20 row (~56 mm) sets the minimum
BOARD_H = 41.5      # mm; J1 (~14.7 + its pin 1 arrow) + left column (3 × 8.5) set the minimum
HOLE_INSET = 3.5    # mm from the top edge / J1 to the mounting-hole centers
MAX_PART_H = 9.5    # mm above the board; documented budget (J1 ≈ 9.1 is the tallest), not enforced
C1_BODY = (8.0, 12.0)  # mm, diameter × length of C1 lying flat: silkscreen outline + footprint keep-out
POWER_TRACK = 1.0   # mm, 5V_IN / 5V_SYS / GND
SIGNAL_TRACK = 0.25 # mm, everything else
POWER_NETS = {"5V_IN", "5V_SYS"}
ROUTE_ORDER = ["5V_IN", "5V_SYS", "3V3", "SPI_SCLK", "SPI_MOSI", "LCD_CS", "LCD_DC", "LCD_RST",
               "BTN_PLAY", "BTN_PREV", "BTN_NEXT", "BTN_VOLUP", "BTN_VOLDN", "BTN_MENU", "PWR_KEY"]

W, H = BOARD_W, BOARD_H
MOUTH = 0.35   # mm the courtyard sits past the edge: body ~flush, its silkscreen still inside
COL = 8.5      # mm, pitch of the J2/J6/J3 column (XH-2 courtyard 8.49)
J1_TOP = H + MOUTH - 15.22     # J1 courtyard top; everything else sits above it
HOLE_X = 15.8  # mm from the left/right edge: between the side connectors and J5 / C1
# ref → (courtyard center x, y in mm from the board's top-left, rotation°, side).
# Rotation sets the mouth direction on the back: XH 0 up / 90 left / 270 right, J1 270 down.
PLACEMENT = {
    "J1": (W / 2, H + MOUTH - 7.61, 270, "back"),     # Pi ribbon leaves downward; pin 1 left
    "J5": (W / 2, -MOUTH + 6.3, 0, "back"),           # display cable leaves upward
    "J2": (-MOUTH + 6.3, COL / 2, 90, "back"),        # left column, wires leave to the left
    "J6": (-MOUTH + 6.3, COL * 1.5, 90, "back"),
    "J3": (-MOUTH + 6.3, COL * 2.5, 90, "back"),
    "J4": (W + MOUTH - 6.3, 23.49 / 2, 270, "back"),  # buttons, right edge, top; wires leave to the right
    "C1": (W / 2 - 5.75, 18.5, 90, "back"),           # leads on the left, body lies to the right
    "C2": (HOLE_X, 13.15, 90, "back"),
    "TP1": (W - HOLE_X + 0.3, 9.5, 0, "back"),
    "TP2": (W - HOLE_X + 0.3, 13.0, 0, "back"),
    "TP3": (W - HOLE_X + 0.3, 16.5, 0, "back"),
    "H1": (HOLE_X, HOLE_INSET, 0, "front"),
    "H2": (W - HOLE_X, HOLE_INSET, 0, "front"),
    "H3": (HOLE_X, J1_TOP - HOLE_INSET, 0, "front"),
    "H4": (W - HOLE_X, J1_TOP - HOLE_INSET, 0, "front"),
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


def c1_body(board, fp):
    """C1 lies flat: outline its body on B.SilkS and keep other footprints off it. The footprint's own
    circle (silkscreen + courtyard) covers the bent leads, so the outline and keep-out start past it."""
    pads = [(pcbnew.ToMM(p.GetPosition().x) - pcbgen.ORIGIN[0], pcbnew.ToMM(p.GetPosition().y) - pcbgen.ORIGIN[1]) for p in fp.Pads()]
    px, cy, r = pads[0][0], (pads[0][1] + pads[1][1]) / 2, C1_BODY[0] / 2  # pads stacked vertically
    x0, x1 = px + r + 0.45, px + 1.0 + C1_BODY[1]
    rect = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECT)
    rect.SetStart(pcbgen.pt(x0, cy - r))
    rect.SetEnd(pcbgen.pt(x1, cy + r))
    rect.SetLayer(pcbnew.B_SilkS)
    rect.SetWidth(FromMM(0.12))
    board.Add(rect)
    zone = pcbnew.ZONE(board)
    zone.SetIsRuleArea(True)
    zone.SetDoNotAllowFootprints(True)
    for flag in ("Tracks", "Vias", "Pads", "ZoneFills"):
        getattr(zone, f"SetDoNotAllow{flag}")(False)
    zone.SetLayer(pcbnew.B_Cu)
    for x, y in ((x0, cy - r - 0.3), (x1 + 0.5, cy - r - 0.3), (x1 + 0.5, cy + r + 0.3), (x0, cy + r + 0.3)):
        zone.AppendCorner(pcbgen.pt(x, y), -1)
    board.Add(zone)


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
    c1_body(board, footprints["C1"])
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
