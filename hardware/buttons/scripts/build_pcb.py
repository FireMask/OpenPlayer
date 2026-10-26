"""Write openplayer-buttons.kicad_pcb from netlist.py: outline, placement, silkscreen, nets, routing.

Needs KiCad's bundled Python (pcbnew):
  "C:/Program Files/KiCad/10.0/bin/python.exe" hardware/buttons/scripts/build_pcb.py
The strip runs top (y = 0, connector end) to bottom. Its length follows from the parameters below;
change them and rerun to resize.
"""

import sys
from pathlib import Path

import pcbnew
from pcbnew import FromMM

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_sch import BOARD_DIR, NAME  # noqa: E402  (also puts hardware/common on sys.path)
import pcbgen  # noqa: E402
from netlist import DESCRIPTIONS, PARTS, pin_net  # noqa: E402
from pcbgen import box, text  # noqa: E402

BTN_PITCH = 10.0   # mm, switch center to center within a group
GROUP_GAP = 4.0    # mm, extra space between groups
GROUPS = [["SW1"], ["SW2", "SW3"], ["SW4", "SW5", "SW6", "SW7"]]  # top to bottom
BOARD_W = 14.0     # mm, strip width
END_MARGIN = 5.5   # mm, from the last switch / connector to the board end (holes sit here; the M2 hole courtyard is 5 mm)

# Courtyard lengths along the strip, from the footprints as placed below.
J1_LEN = 23.5      # XH-8, pins along the strip
SW_LEN = 9.59      # SW_PUSH_6mm turned 90°: pin 1 pads on the left, GND pads on the right

SIGNAL_TRACK = 0.25  # mm, all signals; GND is the pour
# Signals on F.Cu (B.Cu only for short hops), GND pour on B.Cu plus F.Cu stitching.
ROUTE_ORDER = ["BTN_MENU", "BTN_NEXT", "BTN_PLAY", "BTN_PREV", "BTN_VOLDN", "BTN_VOLUP", "PWR_KEY"]  # longest first

TEXT = 1.0   # mm, button and board names
SMALL = 0.8  # mm, pin labels; JLCPCB / KiCad minimum
PIN_LABELS = ["GND", "PLAY", "PREV", "NEXT", "VOL+", "VOL-", "MENU", "KEY"]


def layout():
    """Switch center y per ref, and the board length. J1 is a group of its own above SW1."""
    y = END_MARGIN + J1_LEN + GROUP_GAP + SW_LEN / 2
    centers = {}
    for group in GROUPS:
        for ref in group:
            centers[ref] = y
            y += BTN_PITCH
        y += GROUP_GAP
    length = y - BTN_PITCH - GROUP_GAP + SW_LEN / 2 + END_MARGIN
    return centers, round(length, 2)


CENTERS, BOARD_L = layout()
W, H = BOARD_W, BOARD_L
# ref → (courtyard center x, y in mm from the board's top-left, rotation°, side).
PLACEMENT = {
    "J1": (W / 2, END_MARGIN + J1_LEN / 2, 270, "back"),  # pin 1 at the top
    **{ref: (W / 2, y, 90, "front") for ref, y in CENTERS.items()},
    "H1": (W / 2, END_MARGIN / 2, 0, "front"),
    "H2": (W / 2, H - END_MARGIN / 2, 0, "front"),
}


def silkscreen(board, footprints):
    for fp in footprints.values():
        fp.Reference().SetVisible(False)  # our own labels replace them
    for ref, y in CENTERS.items():  # front: name beside each switch, on the GND side
        text(board, PARTS[ref][0], W - 1.6, y, False, TEXT, angle=90)
    left, top, right, bottom = box(footprints["J1"])
    for pad in footprints["J1"].Pads():  # back: pin labels right of J1 (mirrored, so they read from the back)
        y = pcbnew.ToMM(pad.GetPosition().y) - pcbgen.ORIGIN[1]
        text(board, PIN_LABELS[int(pad.GetNumber()) - 1], (right + W) / 2, y, True, SMALL)
    pin1 = pcbnew.ToMM(footprints["J1"].FindPadByNumber("1").GetPosition().y) - pcbgen.ORIGIN[1]
    text(board, "◂1", left / 2, pin1, True, TEXT)  # points at pin 1 when read from the back
    text(board, "J1 CARRIER", left / 2, (top + bottom) / 2 + 2, True, TEXT, angle=90)
    sw = [CENTERS["SW4"], CENTERS["SW7"]]  # long text along the playback group, back, left edge
    text(board, "OpenPlayer buttons Rev A", 1.6, sum(sw) / 2, True, TEXT, angle=90)


def build():
    board = pcbnew.CreateEmptyBoard()
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    owner = pin_net()
    nets = {}
    for name in owner.values():
        if name not in nets:
            nets[name] = pcbnew.NETINFO_ITEM(board, f"/{name}")  # local labels → /NAME
            board.Add(nets[name])
    pcbgen.outline(board, W, H)
    footprints = pcbgen.place(board, nets, NAME, PARTS, owner, PLACEMENT, descriptions=DESCRIPTIONS)
    silkscreen(board, footprints)
    ds.m_CopperEdgeClearance = FromMM(pcbgen.EDGE_CLEARANCE)
    router = pcbgen.Router(footprints, W, H, ("J1", "1"), SIGNAL_TRACK)
    for net in ROUTE_ORDER:
        router.route_net(board, net, nets[net])
    pcbgen.pour(board, nets["GND"], router.stitch(board, nets["GND"]), W, H)
    path = BOARD_DIR / f"{NAME}.kicad_pcb"
    pcbgen.save(board, nets, footprints, path)
    return path


if __name__ == "__main__":
    print(f"wrote {build().name} ({BOARD_W} x {BOARD_L} mm)")
