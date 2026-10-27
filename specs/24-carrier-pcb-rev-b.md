# SPEC 24 — Carrier PCB Rev B (thin, right-angle connectors)

> **Status:** Approved
> **Depends on:** SPEC 22 (carrier Rev A, nets, generator scripts), SPEC 23 (shared `pcbgen`, button board XH-8 pinout)
> **Date:** 2026-10-26
> **Objective:** Rework the carrier into a single-sided, smaller Rev B where everything stays ≤ 11 mm thick (board plus parts). It uses a right-angle IDC header, JST-XH side-entry connectors and an off-board display cable, and is regenerated in place by the existing scripts with the same nets.

## Scope

**In:**

- **Rev B carrier, regenerated in place** in `hardware/pcb/` by the existing `netlist.py` / `build_sch.py` / `build_pcb.py` and `common/export-fab.ps1`. Rev A survives only in git history.
- **Thickness budget:** board 1.6 mm plus the tallest part ≤ 9.5 mm, so ≤ 11 mm in total. The spec lists the datasheet height of every part.
- **Single-sided:** every part on the back. The front has only copper, silkscreen and the mounting holes.
- **Connector changes (footprints only, same nets and pins):**
  - J1 PI → 2×20 shrouded IDC, **right-angle** (horizontal), on the bottom edge with the ribbon leaving downward.
  - J2 PWR_IN, J3 KEY, J6 SWITCH → JST-XH 2 **side-entry** (S2B-XH-A), on the left edge, upper part, wires leaving to the left.
  - J4 BUTTONS → JST-XH 8 side-entry (S8B-XH-A), on the right edge, upper part, wires leaving to the right. Pinout unchanged, so it stays compatible with the button board.
  - J5 DISPLAY → JST-XH 7 side-entry (S7B-XH-A), centered on the top edge, wires leaving upward. Same pin order as Rev A (1 VCC … 7 RST).
- **C1** keeps a radial footprint but is mounted **lying flat**: leads bent 90°, with a silkscreen outline and a keep-out over the body area.
- **Smaller board:** `BOARD_W` / `BOARD_H` stay parameters, set as small as placement, routing and DRC allow (~60 × 41.5 mm: J1 + the 3 × XH-2 left column set the height). Four M2.5 holes in an inboard rectangle (J1 covers the full bottom width, the connectors take the top corners).
- **Silkscreen:** "Rev B", connector names, J4/J5 pin labels, pin 1 markers, C1 outline, and the micro-USB warning.
- **Checks:** ERC 0, DRC + parity 0/0/0, exported netlist = `NETS`, and the `player.json` self-check still OK. New fabrication output in `hardware/pcb/fabrication/`.
- **Docs:**
  - `hardware/pcb/README.md`: Rev B, connector table, display cable.
  - `docs/pcb-requirements.md` §7 layout: single-sided, edges, thickness budget, charger at the **top** of the case, Pi beside or under the carrier.
  - The display cable is documented: XH-7 → 1×7 Dupont female onto the GC9A01, straight pin order.

**Out of scope:**

- Changes to nets or GPIO, `src/`, `config/`, or the button board.
- Enclosure design, and the decision to stack the Pi or put it beside the carrier (the board works either way).
- Ordering, assembly and bring-up of Rev B.
- Making the cables (only documented).
- Changing the connector family (PH/SH), adding a display power switch, battery sense, or the USB DAC.
- Changes to `pcbgen.py`, except what Rev B strictly needs (e.g. a keep-out helper for C1).

## Data model

### Nets

Unchanged. `NETS`, `BCM_TO_PIN`, `CONFIG_NETS` and `FIXED_NETS` in `netlist.py` are not touched. The self-check against `player.example.json` still has to print `OK`.

### Parts (`netlist.py` `PARTS`): footprint changes only

| Ref | Value | Footprint Rev B | Height above board |
|---|---|---|---|
| J1 | Pi_40pin_IDC | `Connector_IDC:IDC-Header_2x20_P2.54mm_Horizontal` | ≈ 9.0 mm |
| J2, J3, J6 | PWR_IN / KEY / SWITCH | `Connector_JST:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal` | ≈ 7.0 mm |
| J4 | BUTTONS | `Connector_JST:JST_XH_S8B-XH-A_1x08_P2.50mm_Horizontal` | ≈ 7.0 mm |
| J5 | DISPLAY | `Connector_JST:JST_XH_S7B-XH-A_1x07_P2.50mm_Horizontal` | ≈ 7.0 mm |
| C1 | **470uF 10V** (was 1000 µF) | **`Capacitor_THT:CP_Radial_D8.0mm_P3.50mm`**, lying flat | ≈ 8.0 mm (Ø8) |
| C2 | 100nF | unchanged (`C_Disc_D5.0mm_W2.5mm_P5.00mm`) | ≈ 7 mm |
| TP1–3 | — | unchanged (THT pad) | ~0 |
| H1–H4 | M2.5 | unchanged | — |

- The heights are approximate. Step 1 confirms each one against its datasheet and records it in the README. Rule: the tallest part is ≤ 9.5 mm.
- **C1:** Ø8 × ~11.5 mm, 470 µF / 10 V. That is inside the 470–1000 µF range from SPEC 22 and stays optional. Lying flat, it fits the budget; Ø10 would not.

### `build_pcb.py` parameters

```python
BOARD_W = 60.0        # mm; J1's 2×20 row (~56 mm) sets the minimum
BOARD_H = 41.5        # mm; J1 (~14.7 + pin 1 arrow) + left column (3 × 8.5) set the minimum
HOLE_INSET = 3.5      # unchanged
MAX_PART_H = 9.5      # mm, documented thickness budget (not enforced by script)
C1_BODY = (8.0, 12.0) # mm, keep-out + silkscreen outline of the flat-lying C1 body
```

- `PLACEMENT`: every part on `"back"`. J1 is at the bottom center with its mouth toward the bottom edge, J5 at the top center facing up, J2/J6/J3 in a column on the left edge facing left, and J4 on the right edge, upper part, facing right.
- Side-entry mouths sit flush with the board edge (or overhang it by ≤ 0.5 mm), so the plug can enter.

## Implementation plan

1. **Heights and footprints.** Look up the datasheet heights for J1 (IDC horizontal), S2B/S7B/S8B-XH-A, C1 Ø8 and C2. If any exceeds 9.5 mm, stop and report. Update `PARTS` in `netlist.py` (footprints, C1 value). Check: `netlist.py` → `OK`.
2. **Schematic.** Rerun `build_sch.py`, adjusting `POSITIONS` only if needed. Check: ERC 0, exported netlist = `NETS`.
3. **Placement.** `build_pcb.py`: all parts on the back, Rev B edges (J1 bottom, J5 top center, J2/J6/J3 left, J4 right-top), mouths at the edge, C1 flat with its keep-out + outline, holes inboard (top pair beside J5, bottom pair above J1), `BOARD_H` reduced. Check: DRC shows only "unconnected" items, and no courtyard overlaps the edge except connector mouths.
4. **Routing.** Same `Router` and GND pour. If routing fails, raise `BOARD_H` 1 mm at a time until it passes, and record the final value. Check: DRC + parity 0/0/0.
5. **Silkscreen.** "Rev B", J1–J6 names, J4/J5 pin labels, pin 1 markers, C1 outline + polarity, micro-USB warning. All on the back or front, readable, ≥ 0.8 mm. Check: DRC still 0/0/0 (no silk-over-pad).
6. **Fabrication.** `export-fab.ps1 -Board pcb` regenerates Gerbers/drill zip, BOM and renders. Check: it finishes with no errors.
7. **Docs.**
   - `hardware/pcb/README.md`: Rev B, connector table with types, heights and thickness, display cable XH-7 → Dupont 1×7, C1 lying flat.
   - `docs/pcb-requirements.md` §7: single-sided layout, edges, ≤ 11 mm budget, charger at the top, Pi beside or under.

## Acceptance criteria

- [ ] `python hardware/pcb/scripts/netlist.py` prints `OK`, and `NETS` is identical to Rev A's (diff of the dict = empty).
- [ ] `kicad-cli sch erc` reports 0 errors.
- [ ] `kicad-cli pcb drc --schematic-parity` reports 0 violations / 0 unconnected / 0 parity issues.
- [ ] The exported netlist matches `NETS` exactly.
- [ ] Every footprint is on the back. The front has no component (only holes, copper, silkscreen).
- [ ] J1 is `IDC-Header_2x20_P2.54mm_Horizontal` at the bottom center, with the mouth toward the bottom edge.
- [ ] J5 is S7B-XH-A at the top center, mouth up. J2/J3/J6 are S2B-XH-A on the left edge, mouth left. J4 is S8B-XH-A on the right edge, upper part, mouth right.
- [ ] J4 pin N carries the same net as Rev A (button board compatible). `hardware/buttons/scripts/netlist.py` → `OK`.
- [ ] J5 pin order: 1 VCC, 2 GND, 3 SCL, 4 SDA, 5 DC, 6 CS, 7 RST.
- [ ] C1 is `CP_Radial_D8.0mm_P3.50mm` 470 µF / 10 V, with a silkscreen outline of the flat body and a keep-out.
- [ ] The README lists each part's datasheet height, and no part exceeds 9.5 mm.
- [ ] The board is `BOARD_W` × `BOARD_H` with `BOARD_H` < 45 mm (Rev A) and four M2.5 holes inboard (not in courtyard conflict with any connector).
- [ ] The silkscreen shows "Rev B", J1–J6 names, J4/J5 pin labels, pin 1 markers and the micro-USB warning. "Rev A" appears nowhere.
- [ ] `export-fab.ps1 -Board pcb` finishes without errors. `fabrication/` contains the Gerber + drill zip, BOM CSV and two renders.
- [ ] `hardware/pcb/README.md` describes Rev B and the display cable. `docs/pcb-requirements.md` §7 shows the single-sided layout, the ≤ 11 mm budget and the charger at the top.
- [ ] No file under `src/`, `config/` or `hardware/buttons/` changes (except the regenerated `.kicad_pro` churn, reverted).

## Decisions

- **Yes:** carrier budget ≤ 11 mm (1.6 board + ≤ 9.5 parts), within a whole player of 17 ± 2 mm.
- **Yes:** keep the 40-pin ribbon, with a right-angle IDC header so it leaves flat. Pogo pins, direct-solder and a Pi HAT stack were rejected: they're more fragile or thicker.
- **No:** sandwiching the Pi under the carrier as the default. Carrier + Pi + header/socket ≈ 27 mm doesn't fit 17 mm. J1 at the bottom edge still allows it later.
- **Yes:** JST-XH side-entry (S*B-XH-A) for J2/J3/J4/J6. Same family and same cables, wire parallel to the board. **No:** PH/SH (new crimps, out of scope).
- **Yes:** display off-board on an XH-7 → Dupont 1×7 cable, same pin order. A 1×7 front header plus the module was too thick.
- **Yes:** J5 at the top center, J2/J3/J6 on the left edge, J4 on the right edge, upper part. Everything on the top edge would need ~70 mm, so the board would widen.
- **Yes:** single-sided, all parts on the back. The front is flat against the case/display.
- **Yes:** C1 → 470 µF / 10 V Ø8, lying flat (radial footprint, bent leads, outline + keep-out). Ø10 flat = 10 mm > budget. **No:** axial electrolytic (hard to find).
- **Yes:** charger at the top of the case. This updates the SPEC 23 assumption (charger at the bottom); battery placement is free, since it wires only to the module.
- **Yes:** Rev B in place in `hardware/pcb/`, Rev A only in git. A single active board, scripts unchanged.
- **Yes:** nets, GPIO and the J4 pinout are frozen. No change to `src/`, `config/` or the button board.
- **Yes:** `BOARD_H` is reduced until DRC fails, then the smallest passing value is kept. `BOARD_W` stays 60 because of J1.
- **Yes:** holes inboard, 60 × 41.5 (decided in step 3). The horizontal J1 courtyard (59.6 mm) covers the bottom corners and the connectors take the top ones. **No:** widening to ~72 mm for corner holes, or using only 2 holes.

## Risks

| Risk | Mitigation |
|---|---|
| A real part height exceeds 9.5 mm (the right-angle IDC is ≈ 9 mm, close to the limit). | Step 1 checks the datasheets before touching the PCB. If one exceeds the limit, stop and choose another part or raise the budget with the user. |
| The plug of a side-entry connector doesn't fit because the mouth is set back from the edge or blocked by a hole. | Mouths at the edge (≤ 0.5 mm overhang); holes kept clear of the connector fronts; checked visually in the renders. |
| At 60 × ~32 mm, the router can't route all nets on 2 layers. | Raise `BOARD_H` 1 mm at a time (step 4). The second option is to move C2/TPs. |
| C1's bent leads break, or the body rubs on other parts. | Keep-out + silkscreen outline of the body, populate optional, polarity marked. |
| The display cable gets made reversed (XH-7 ↔ Dupont). | Same pin order, pin 1 marked, cable described in the README; check continuity before connecting. |
| A long display SPI cable (~10–15 cm) causes noise or artifacts. | Short cable; GND next to the signals on the connector; lower the SPI clock in `player.json` if it fails (no code change). |
| The ribbon leaving horizontally collides with the case or the Pi. | J1 at the bottom center; the Pi position is decided with the case (out of scope). The board works beside or stacked. |
| Moving the charger to the top contradicts SPEC 23/docs. | Update `docs/pcb-requirements.md` §7 in step 7. The button board doesn't depend on it. |

## What is **not** in this spec

- Changes to nets, GPIO, `src/`, `config/` or the button board.
- The enclosure and the final Pi position (beside / stacked).
- Ordering, assembly and bring-up of Rev B.
- Making the cables (display, buttons, power).
- PH/SH connectors, display power switch, battery sense, USB DAC.

Each one, if it lands, goes in its own spec.
