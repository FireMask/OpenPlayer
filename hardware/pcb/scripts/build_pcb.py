"""Write openplayer-carrier.kicad_pcb from netlist.py: outline, placement, silkscreen, nets, routing.

Needs KiCad's bundled Python (pcbnew):
  "C:/Program Files/KiCad/10.0/bin/python.exe" hardware/pcb/scripts/build_pcb.py
Positions are relative to BOARD_W / BOARD_H; change them and rerun to resize.
Rev C (SPEC 25): Pi Zero plugged into J1 on the back (HAT style), GC9A01 module soldered on the front,
every cable connector on the back with its mouth at a board edge.
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

BOARD_W = 65.0      # mm; the Pi Zero's width
BOARD_H = 53.0      # mm; Pi (30) + the band above it, which J4 (23.5 long) needs on the right edge
MAX_PART_H = 10.5   # mm, back part + Pi part under it; documented budget (README), not enforced
C1_BODY = (8.0, 12.0)  # mm, diameter × length of C1 lying flat: silkscreen outline + footprint keep-out
POWER_TRACK = 1.0   # mm, 5V_IN / 5V_SYS / GND
SIGNAL_TRACK = 0.25 # mm, everything else
POWER_NETS = {"5V_IN", "5V_SYS"}
ROUTE_ORDER = ["5V_IN", "5V_SYS", "3V3", "SPI_SCLK", "SPI_MOSI", "LCD_CS", "LCD_DC", "LCD_RST",
               "BTN_PLAY", "BTN_PREV", "BTN_NEXT", "BTN_VOLUP", "BTN_VOLDN", "BTN_MENU", "PWR_KEY"]

W, H = BOARD_W, BOARD_H
MOUTH = 0.35   # mm the courtyard sits past the edge: body ~flush, its silkscreen still inside
COL = 8.5      # mm, pitch of the J2/J6 column (XH-2 courtyard 8.49)
# Pi Zero 2 W (official mechanical drawing), seen from the front through the board: its component side
# faces the carrier, so the drawing applies unmirrored. Outline flush with the bottom edge.
PI_W, PI_H = 65.0, 30.0
PI_TOP = H - PI_H
PI_HOLES = [(3.5, PI_TOP + 3.5), (61.5, PI_TOP + 3.5), (3.5, H - 3.5), (61.5, H - 3.5)]  # 58 × 23
PI_PIN1 = (W / 2 - 9.5 * 2.54, PI_TOP + 3.5 + 1.27)  # left end, inner row; pin 2 on the edge row
ANTENNA = (18.0, H - 7.0, 37.0, H)  # x0, y0, x1, y1: between the mini-HDMI and USB OTG ports; no pour
# GC9A01 module on the front: pin row 2 mm above its bottom edge (= board edge), screen 25 mm above the row.
LCD_ROW = H - 2.0
LCD_CENTER = (W / 2, LCD_ROW - 25.0)
LCD_R, LCD_TAB = 18.0, 23.0   # mm, round body radius, bottom tab width
LCD_HOLES = [(W / 2 - 9.6, LCD_ROW - 3.5), (W / 2 + 9.6, LCD_ROW - 3.5)]  # tab holes, 19.2 c-c
J4_LEN = 23.5  # mm, XH-8 courtyard along the edge
# ref → (courtyard center x, y in mm from the board's top-left, rotation°, side).
# Rotation sets the mouth direction on the back: XH 0 up / 90 left / 270 right.
PLACEMENT = {
    "J1": (W / 2, PI_TOP + 3.5, 270, "back"),         # Pi socket; pin 1 left, pin 2 above it
    "J5": (W / 2, LCD_ROW, 270, "front"),             # module header holes; pin 1 (VCC) rightmost
    "J2": (-MOUTH + 6.3, COL / 2, 90, "back"),        # left column, wires leave to the left
    "J6": (-MOUTH + 6.3, COL * 1.5, 90, "back"),
    "J3": (-MOUTH + 6.3, PI_TOP + 3.5 + 1.27 + 1.81 + COL / 2 + 0.05, 90, "back"),  # left, between H1 and H3
    "J4": (W + MOUTH - 6.3, PI_TOP + 0.42 - J4_LEN / 2, 270, "back"),  # right edge, above H2 / J1
    "J7": (18.0, -MOUTH + 6.3, 0, "back"),            # power key, wires leave upward
    "C1": (20.0, 18.0, 90, "back"),                   # leads on the left, body lies to the right
    "C2": (36.5, 18.0, 90, "back"),
    "TP1": (43.0, 14.0, 0, "back"),                   # inside the display outline, clear of its silkscreen
    "TP2": (43.0, 17.5, 0, "back"),
    "TP3": (43.0, 21.0, 0, "back"),
    **{f"H{i + 1}": (x, y, 0, "front") for i, (x, y) in enumerate(PI_HOLES)},
    "H5": (*LCD_HOLES[0], 0, "front"),
    "H6": (*LCD_HOLES[1], 0, "front"),
}
NAMES = {"J1": "PI", "J2": "PWR_IN", "J3": "KEY", "J4": "BUTTONS", "J5": "DISPLAY", "J6": "SWITCH",
         "TP1": "GND", "TP2": "5V", "TP3": "3V3"}
PIN_LABELS = {
    "J4": ["GND", "PLAY", "PREV", "NEXT", "VOL+", "VOL-", "MENU", "KEY"],
    "J5": ["VCC", "GND", "SCL", "SDA", "DC", "CS", "RST"],
}
TEXT = 0.9   # mm, connector names
SMALL = 0.8  # mm, pin labels; JLCPCB / KiCad minimum


def pads(fp):
    """[(label index, x, y)] of a connector's pads, in mm from the board's top-left."""
    return [(int(p.GetNumber()) - 1, pcbnew.ToMM(p.GetPosition().x) - pcbgen.ORIGIN[0],
             pcbnew.ToMM(p.GetPosition().y) - pcbgen.ORIGIN[1]) for p in fp.Pads()]


def silkscreen(board, footprints):
    """Names on B.SilkS (the parts' side), never under a connector body (it would be hidden). J4/J5 pin
    labels and the micro-USB warning go on the bare front: no room on the back at pin height."""
    for fp in footprints.values():
        fp.Reference().SetVisible(fp.GetReference().startswith("C"))  # our own labels replace the rest
    for ref in ("J2", "J6", "J3"):  # vertical, in the strip right of the column
        left, top, right, bottom = box(footprints[ref])
        text(board, f"{ref} {NAMES[ref]}", right + 1.0, (top + bottom) / 2, True, SMALL, angle=90)
    left, top, right, bottom = box(footprints["J4"])
    for i, x, y in pads(footprints["J4"]):
        text(board, PIN_LABELS["J4"][i], x + 5.0, y, False, SMALL)
    text(board, "J4 BUTTONS", (left + right) / 2, bottom + 1.4, True, TEXT)
    left, top, right, bottom = box(footprints["J5"])
    for i, x, y in pads(footprints["J5"]):
        text(board, PIN_LABELS["J5"][i], x, y - 5.5, False, SMALL, angle=90)
    text(board, "J5 DISPLAY", (left + right) / 2, bottom + 1.0, True, TEXT)
    for ref in ("TP1", "TP2", "TP3"):  # names to the left
        left, top, right, bottom = box(footprints[ref])
        text(board, NAMES[ref], left - 1.6, (top + bottom) / 2, True, SMALL)
    top = box(footprints["J1"])[1]  # strip between H3 and H4, above J1's pins
    text(board, "OpenPlayer carrier Rev B", W / 2, top - 2.6, True, 1.0)
    text(board, "J1 PI  (pin 1 ▸)", W / 2, top - 1.0, True, TEXT)
    text(board, "OpenPlayer Rev B", W / 2, top + 7.5, False, 1.0)  # front, behind J1's body
    text(board, "DO NOT USE PI MICRO-USB POWER WHILE CONNECTED", W / 2, top + 10.5, False, SMALL)


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


def shape(board, kind, layer, *points, width=0.12):
    s = pcbnew.PCB_SHAPE(board, kind)
    if kind == pcbnew.SHAPE_T_ARC:
        s.SetArcGeometry(*(pcbgen.pt(*p) for p in points))
    elif kind == pcbnew.SHAPE_T_CIRCLE:
        s.SetCenter(pcbgen.pt(*points[0]))
        s.SetEnd(pcbgen.pt(points[0][0] + points[1], points[0][1]))
    else:
        s.SetStart(pcbgen.pt(*points[0]))
        s.SetEnd(pcbgen.pt(*points[1]))
    s.SetLayer(layer)
    s.SetWidth(FromMM(width))
    board.Add(s)


def pi_overlay(board, fp):
    """Pi outline + pin 1 on User.Drawings, and the check that J1 lands pin for pin on the Pi's header."""
    shape(board, pcbnew.SHAPE_T_RECT, pcbnew.Dwgs_User, (0, PI_TOP), (PI_W, H))
    shape(board, pcbnew.SHAPE_T_CIRCLE, pcbnew.Dwgs_User, PI_PIN1, 1.0)
    for n in range(1, 41):  # odd pins on the inner row, even pins on the edge row, pin 1 at the left
        x, y = PI_PIN1[0] + (n - 1) // 2 * 2.54, PI_PIN1[1] - (n + 1) % 2 * 2.54
        p = fp.FindPadByNumber(str(n)).GetPosition()
        got = (pcbnew.ToMM(p.x) - pcbgen.ORIGIN[0], pcbnew.ToMM(p.y) - pcbgen.ORIGIN[1])
        assert abs(got[0] - x) < 0.01 and abs(got[1] - y) < 0.01, f"J1 pin {n} at {got}, Pi pin {n} at {(x, y)}"


# H5/H6 sit under the module's own tab holes, 3.5 mm from its header: the module, not the courtyards,
# reserves that space, and the stock M2 courtyard (r 2.5) overlaps J5's. Waive only that pair.
DRC_RULES = """(version 1)
(rule "display standoffs beside the display header"
  (constraint courtyard_clearance)
  (condition "(A.Reference == 'J5' && (B.Reference == 'H5' || B.Reference == 'H6')) || (B.Reference == 'J5' && (A.Reference == 'H5' || A.Reference == 'H6'))")
  (severity ignore))
"""


def display_outline(board):
    """GC9A01 module on F.SilkS: round body + bottom tab (the tab's bottom is the board edge)."""
    cx, cy = LCD_CENTER
    dx = LCD_TAB / 2
    dy = (LCD_R ** 2 - dx ** 2) ** 0.5
    shape(board, pcbnew.SHAPE_T_ARC, pcbnew.F_SilkS, (cx + dx, cy + dy), (cx, cy - LCD_R), (cx - dx, cy + dy))
    for x in (cx - dx, cx + dx):
        shape(board, pcbnew.SHAPE_T_SEGMENT, pcbnew.F_SilkS, (x, cy + dy), (x, H - 0.3))


def antenna_keepout(board):
    """No copper pour on either layer over the Pi's Wi-Fi/BT antenna; pads and tracks may cross it."""
    zone = pcbnew.ZONE(board)
    zone.SetIsRuleArea(True)
    for flag in ("Tracks", "Vias", "Pads", "Footprints"):
        getattr(zone, f"SetDoNotAllow{flag}")(False)
    zone.SetDoNotAllowZoneFills(True)
    lset = pcbnew.LSET()
    for layer in pcbgen.layers():
        lset.AddLayer(layer)
    zone.SetLayerSet(lset)
    x0, y0, x1, y1 = ANTENNA
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        zone.AppendCorner(pcbgen.pt(x, y), -1)
    zone.SetZoneName("PI_ANTENNA")
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
    pi_overlay(board, footprints["J1"])
    silkscreen(board, footprints)
    display_outline(board)
    c1_body(board, footprints["C1"])
    antenna_keepout(board)
    ds.m_CopperEdgeClearance = FromMM(pcbgen.EDGE_CLEARANCE)
    router = pcbgen.Router(footprints, W, H, ("J1", "1"), SIGNAL_TRACK, POWER_TRACK, POWER_NETS)
    for net in ROUTE_ORDER:
        router.route_net(board, net, nets[net])
    pcbgen.pour(board, nets["GND"], router.stitch(board, nets["GND"]), W, H)
    path = PCB_DIR / f"{NAME}.kicad_pcb"
    pcbgen.save(board, nets, footprints, path)
    path.with_suffix(".kicad_dru").write_text(DRC_RULES, encoding="utf-8")
    return path


if __name__ == "__main__":
    print(f"wrote {build().name} ({BOARD_W} x {BOARD_H} mm)")
