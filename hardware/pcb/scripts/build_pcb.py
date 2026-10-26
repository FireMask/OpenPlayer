"""Write openplayer-carrier.kicad_pcb from netlist.py: outline, placement, silkscreen, nets, routing.

Needs KiCad's bundled Python (pcbnew):
  "C:/Program Files/KiCad/10.0/bin/python.exe" hardware/pcb/scripts/build_pcb.py
Positions are relative to BOARD_W / BOARD_H; change them and rerun to resize.
"""

import heapq
import math
import os
import sys
from pathlib import Path

import numpy as np
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
EDGE_CLEARANCE = 0.5  # mm, copper to board edge (KiCad default rule)
VIA = (0.6, 0.3)      # mm, diameter / drill

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


# --- Routing -------------------------------------------------------------------------------
# A grid router (Dijkstra with bend and via costs) on F.Cu/B.Cu. The grid is aligned to J1 pin 1
# so a 0.25 mm track fits exactly between two header pads. GND is not routed: it is a pour on
# both layers stitched with vias.
GRID = 0.254
MARGIN = 0.05  # mm of slack on every clearance check, covers grid rounding
POWER_NETS = {"5V_IN", "5V_SYS"}
ROUTE_ORDER = ["5V_IN", "5V_SYS", "3V3", "SPI_SCLK", "SPI_MOSI", "LCD_CS", "LCD_DC", "LCD_RST",
               "BTN_PLAY", "BTN_PREV", "BTN_NEXT", "BTN_VOLUP", "BTN_VOLDN", "BTN_MENU", "PWR_KEY"]
# Everything is routed on F.Cu; B.Cu only for short hops, so its GND pour stays nearly solid and
# reaches every GND pad. The F.Cu pour is shielding, tied in through the stitching vias.
B_CU_COST = 4.0
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
BEND = [0, 0.6, 2.0, None, None]  # extra cost per 0/45/90° turn; sharper turns not allowed
VIA_COST = 15


def mm(v):
    return pcbnew.ToMM(v)


class Router:
    def __init__(self, footprints):
        p1 = footprints["J1"].FindPadByNumber("1").GetPosition()
        self.x0 = (mm(p1.x) - ORIGIN[0]) % GRID
        self.y0 = (mm(p1.y) - ORIGIN[1]) % GRID
        self.nx = int((W - self.x0) / GRID) + 1
        self.ny = int((H - self.y0) / GRID) + 1
        self.X, self.Y = np.meshgrid(self.x0 + np.arange(self.nx) * GRID, self.y0 + np.arange(self.ny) * GRID, indexing="ij")
        self.obstacles = []  # (layers, kind, geometry, half_width, net)
        self.pads = {}       # net → [(cx, cy, hx, hy)]
        for fp in footprints.values():
            for pad in fp.Pads():
                bb = pad.GetBoundingBox()
                c = pad.GetPosition()
                cx, cy = mm(c.x) - ORIGIN[0], mm(c.y) - ORIGIN[1]
                hx, hy = mm(bb.GetWidth()) / 2, mm(bb.GetHeight()) / 2
                net = pad.GetNetname().lstrip("/")
                if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    hx = hy = mm(pad.GetDrillSize().x) / 2 + 0.05  # hole clearance is a bit larger
                if net == "GND":  # on B.Cu leave room around GND pads for the pour's thermal spokes
                    self.obstacles.append(((0,), "rect", (cx, cy, hx, hy), 0.0, net))
                    self.obstacles.append(((1,), "rect", (cx, cy, hx, hy), 0.6, net))
                else:
                    self.obstacles.append(((0, 1), "rect", (cx, cy, hx, hy), 0.0, net))
                self.pads.setdefault(net, []).append((cx, cy, hx, hy))

    def xy(self, i, j):
        return self.x0 + i * GRID, self.y0 + j * GRID

    def blocked(self, net, half, own_net_too=False):
        """Per layer: cells where a track of half-width `half` would violate clearance."""
        masks = np.zeros((2, self.nx, self.ny), bool)
        edge = EDGE_CLEARANCE + half + MARGIN
        for m in masks:
            m |= (self.X < edge) | (self.X > W - edge) | (self.Y < edge) | (self.Y > H - edge)
        for layers, kind, g, obs_half, obs_net in self.obstacles:
            if obs_net == net and obs_net and not own_net_too:
                continue
            reach = obs_half + CLEARANCE + half + MARGIN
            if kind == "rect":
                cx, cy, hx, hy = g
                dx = np.maximum(np.abs(self.X - cx) - hx, 0)
                dy = np.maximum(np.abs(self.Y - cy) - hy, 0)
            else:  # segment
                x1, y1, x2, y2 = g
                vx, vy = x2 - x1, y2 - y1
                t = np.clip(((self.X - x1) * vx + (self.Y - y1) * vy) / max(vx * vx + vy * vy, 1e-9), 0, 1)
                dx, dy = self.X - (x1 + t * vx), self.Y - (y1 + t * vy)
            hit = dx * dx + dy * dy < reach * reach
            for layer in layers:
                masks[layer] |= hit
        return masks

    def pad_cells(self, pad, half):
        cx, cy, hx, hy = pad
        inside = (np.abs(self.X - cx) <= hx - half) & (np.abs(self.Y - cy) <= hy - half)
        return {(int(i), int(j)) for i, j in zip(*np.nonzero(inside))}

    def search(self, sources, targets, free, via_ok):
        """Cheapest path from any source cell to any target cell. Cells are (layer, i, j)."""
        tx = [c[1] for c in targets]
        ty = [c[2] for c in targets]
        box = (min(tx), max(tx), min(ty), max(ty))

        def h(i, j):  # octile distance to the targets' bounding box: never overestimates
            dx = max(box[0] - i, 0, i - box[1])
            dy = max(box[2] - j, 0, j - box[3])
            return max(dx, dy) + 0.414 * min(dx, dy)

        layer_cost = (1.0, B_CU_COST)
        best, parent, heap = {}, {}, []
        for c in sources:
            state = (*c, 8)
            best[state] = 0
            heapq.heappush(heap, (h(c[1], c[2]), 0, state))
        while heap:
            _, g, state = heapq.heappop(heap)
            if g > best.get(state, math.inf):
                continue
            layer, i, j, d = state
            if (layer, i, j) in targets:
                path = [(layer, i, j)]
                while state in parent:
                    state = parent[state]
                    path.append(state[:3])
                return path[::-1]
            steps = []
            for nd, (di, dj) in enumerate(DIRS):
                turn = 0 if d == 8 else min(abs(nd - d), 8 - abs(nd - d))
                if BEND[turn] is None:
                    continue
                ni, nj = i + di, j + dj
                if not (0 <= ni < self.nx and 0 <= nj < self.ny) or not free[layer, ni, nj]:
                    continue
                if di and dj and not (free[layer, i + di, j] and free[layer, i, j + dj]):
                    continue  # no corner cutting on diagonals
                cost = (1.414 if di and dj else 1.0) * layer_cost[layer] + BEND[turn]
                steps.append(((layer, ni, nj, nd), cost))
            if via_ok[i, j]:
                steps.append(((1 - layer, i, j, 8), VIA_COST))
            for nxt, cost in steps:
                ng = g + cost
                if ng < best.get(nxt, math.inf):
                    best[nxt] = ng
                    parent[nxt] = state
                    heapq.heappush(heap, (ng + h(nxt[1], nxt[2]), ng, nxt))
        return None

    def route_net(self, board, net, netinfo):
        width = POWER_TRACK if net in POWER_NETS else SIGNAL_TRACK
        half = width / 2
        free = ~self.blocked(net, half)
        via_ok = ~self.blocked(net, VIA[0] / 2).any(axis=0)
        pads = list(self.pads[net])
        done = [pads.pop(0)]
        tree = {}  # (layer, i, j) → pad it belongs to, or None for track cells
        for c in self.pad_cells(done[0], half):
            for layer in (0, 1):
                tree[(layer, *c)] = done[0]
        while pads:
            # next: the pad closest to anything already connected keeps trunks short
            pads.sort(key=lambda p: min(abs(p[0] - q[0]) + abs(p[1] - q[1]) for q in done))
            pad = pads.pop(0)
            sources = {(layer, *c) for c in self.pad_cells(pad, half) for layer in (0, 1)}
            sources = {s for s in sources if free[s]}
            path = self.search(sources, tree, free, via_ok) if sources else None
            if path is None:
                raise RuntimeError(f"cannot route {net} to pad at {pad[:2]}")
            self.emit(board, net, netinfo, path, pad, tree[path[-1]], width)
            for c in path:
                tree.setdefault(c, None)
            for c in self.pad_cells(pad, half):
                for layer in (0, 1):
                    tree.setdefault((layer, *c), pad)
            done.append(pad)

    def emit(self, board, net, netinfo, path, start_pad, end_pad, width):
        points = [(path[0][0], start_pad[0], start_pad[1])]
        points += [(layer, *self.xy(i, j)) for layer, i, j in path]
        if end_pad:
            points.append((path[-1][0], end_pad[0], end_pad[1]))
        keep = [points[0]]  # drop collinear points, keep layer changes
        for a, b in zip(points[1:], points[2:] + [None]):
            prev = keep[-1]
            if b and a[0] == prev[0] == b[0]:
                cross = (a[1] - prev[1]) * (b[2] - a[2]) - (a[2] - prev[2]) * (b[1] - a[1])
                if abs(cross) < 1e-6:
                    continue
            keep.append(a)
        for a, b in zip(keep, keep[1:]):
            if a[0] != b[0]:
                self.via(board, netinfo, a[1], a[2], net)
            elif (a[1], a[2]) != (b[1], b[2]):
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pt(a[1], a[2]))
                track.SetEnd(pt(b[1], b[2]))
                track.SetWidth(FromMM(width))
                track.SetLayer(LAYERS[a[0]])
                track.SetNet(netinfo)
                board.Add(track)
                self.obstacles.append(((a[0],), "seg", (a[1], a[2], b[1], b[2]), width / 2, net))

    def via(self, board, netinfo, x, y, net):
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(pt(x, y))
        via.SetWidth(FromMM(VIA[0]))
        via.SetDrill(FromMM(VIA[1]))
        via.SetNet(netinfo)
        board.Add(via)
        self.obstacles.append(((0, 1), "rect", (x, y, 0, 0), VIA[0] / 2, net))
        return via

    def stitch(self, board, netinfo, pitch=5.0):
        """GND vias on a regular lattice wherever they fit, to tie the two pours together."""
        ok = ~self.blocked("GND", VIA[0] / 2 + 0.3, own_net_too=True).any(axis=0)  # room for the pour
        step = round(pitch / GRID)
        vias = []
        for i in range(step // 2, self.nx, step):
            for j in range(step // 2, self.ny, step):
                if ok[i, j]:
                    vias.append(self.via(board, netinfo, *self.xy(i, j), "GND"))
        return vias


def pour(board, netinfo, stitching):
    """GND zones on both layers; stitching vias the fill doesn't reach on both sides are removed."""
    for layer in LAYERS:
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(netinfo)
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in [(0, 0), (W, 0), (W, H), (0, H)]:
            outline.Append(pt(x, y))
        zone.SetLocalClearance(FromMM(0.3))
        zone.SetMinThickness(FromMM(0.25))
        # pads join the B.Cu pour with thermal spokes; the F.Cu pour keeps clear of pads
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if layer == pcbnew.B_Cu else pcbnew.ZONE_CONNECTION_NONE)
        zone.SetThermalReliefGap(FromMM(0.5))
        zone.SetThermalReliefSpokeWidth(FromMM(0.5))
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(zone)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    zones = list(board.Zones())
    dangling = [v for v in stitching
                if not all(any(z.GetLayer() == layer and z.HitTestFilledArea(layer, v.GetPosition()) for z in zones)
                           for layer in LAYERS)]
    for v in dangling:
        board.Remove(v)
    if dangling:
        board.BuildConnectivity()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())


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
    ds.m_CopperEdgeClearance = FromMM(EDGE_CLEARANCE)
    router = Router(footprints)
    for net in ROUTE_ORDER:
        router.route_net(board, net, nets[net])
    pour(board, nets["GND"], router.stitch(board, nets["GND"]))
    unused = [n for n, item in nets.items() if item.GetNetCode() and not any(
        p.GetNetname() == item.GetNetname() for fp in footprints.values() for p in fp.Pads())]
    for n in unused:
        board.Remove(nets[n])
    path = PCB_DIR / f"{NAME}.kicad_pcb"
    pcbnew.SaveBoard(str(path), board)
    return path


if __name__ == "__main__":
    print(f"wrote {build().name} ({BOARD_W} x {BOARD_H} mm)")
