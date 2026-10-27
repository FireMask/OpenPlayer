# SPEC 25 — Carrier PCB Rev C (Pi sandwich, display on board) + 6-key button strip

> **Status:** Approved
> **Depends on:** SPEC 24 (carrier Rev B, generator scripts), SPEC 23 (button board)
> **Date:** 2026-10-27
> **Objective:** Rework the carrier into a Pi Zero "HAT": the Pi plugs into a 2×20 socket on the carrier's back, and the GC9A01 module is soldered on its front. This fits a portrait, Walkman-size case (80 × 110 × ~33 mm) with a 4000 mAh cell and frees the bottom of the case for the USB OTG / DAC. The button strip loses the POWER key so it fits the case height.

## Case context (drives this spec; enclosure itself out of scope)

- **Portrait case ≈ 80 W × 110 H × 33 D mm** (inside ≈ 74 × 104 × 29). Held in the right hand, so the thumb sits on the right side wall.
- **Battery:** 4000 mAh 3.7 V LiPo, **6 × 60 × 91.5 mm**, flat against the back wall.
- **Front stack, front to back:**

| Layer | mm |
|---|---:|
| Display module (4) + header plastic spacer (2.5) | 6.5 |
| Carrier | 1.6 |
| Gap: 2×20 socket (8.5) + Pi header plastic (2.5) | 11 |
| Pi Zero 2 W board + bottom side | ~2.2 |
| Gap / insulating sheet | 1 |
| Battery | 6 |
| **Total** | **~28.3** |

- **Front view:**
  - Top of the case: carrier + Pi (≈ 45 mm tall).
  - Bottom zone (≈ 55 mm): charger, USB OTG adapter, DAC. Headphone jack and charger USB-C exit the bottom wall.
  - Right wall: the button strip.
  - Top edge: the POWER key.

## Scope

**In:**

- **Rev C carrier, regenerated in place** in `hardware/pcb/` by the existing scripts. Rev B lives only in git.
- **J1 PI** → **2×20 female socket, 2.54 mm, vertical, 8.5 mm**, on the **back**.
  - The Pi plugs in component side up (toward the carrier), like a HAT.
  - J1 pin N = Pi pin N.
- **Pi alignment:** the Pi's outline is aligned to the carrier's **bottom edge**, so its ports (mini-HDMI, USB OTG, PWR) are flush with that edge and face the bottom of the case.
  - Pi header row at the top of the Pi outline.
  - Four **M2.5 holes on the Pi's pattern** (58 × 23, 3.5 mm inset from the Pi outline) carry **11 mm standoffs** shared by both boards.
- **J5 DISPLAY** → the module's pre-soldered **1×7 2.54 mm header goes through the carrier and is soldered on the back**. The module sits on the **front**.
  - Pin order unchanged (1 VCC, 2 GND, 3 SCL, 4 SDA, 5 DC, 6 CS, 7 RST).
  - **Pin 1 (VCC, square pad) is the rightmost pin seen from the front.**
- **Display mounting:** two **M2 holes** for 2.5 mm standoffs under the module's tab holes.
- **New J7 PWR_BTN:** JST-XH 2 side-entry (pin 1 `PWR_KEY`, pin 2 `GND`), wired to a panel momentary key on the case's top edge.
  - J4 keeps its 8-pin pinout, pin 8 `PWR_KEY` included, so the cable is unchanged.
- **Carrier back parts:** J2, J3, J4, J6, J7, C1, C2 and TP1–3 stay on the back, in the 11 mm gap between the boards.
  - Height rule: part height + Pi part height under it ≤ 10.5 mm (0.5 mm air).
  - J4's mouth sits on the right edge (toward the button strip). J2/J3/J6 sit on the left edge, J7 on the top edge.
- **Copper keep-out** (both layers, no pour) over the Pi's Wi-Fi/BT antenna area.
- **Board size:** `BOARD_W` 65 (Pi width). `BOARD_H` ≈ 45, set by the display: its pin row is 2 mm from the module's bottom edge, which is aligned to the carrier's bottom edge.
- **Button board (SPEC 23 files):** remove SW1 (POWER).
  - `GROUPS = [["SW2", "SW3"], ["SW4", "SW5", "SW6", "SW7"]]`, `BTN_PITCH = 9.6`, giving ≈ 100.5 mm (fits 104 mm inside).
  - Its J1 pin 8 (`KEY`) stays in the connector, unconnected on the board.
- **Silkscreen:**
  - "Rev C", connector names, pin 1 markers, the display outline on the front, the micro-USB warning.
  - J4 pin labels move off the area under the display.
- **Checks:** ERC 0, DRC + parity 0/0/0, exported netlist = `NETS`, both `netlist.py` self-checks `OK`. Fab output regenerated for both boards.
- **Docs:**
  - `hardware/pcb/README.md`: Rev C, stack, connector table, heights.
  - `hardware/buttons/README.md`: 6 keys, new length.
  - `docs/pcb-requirements.md`: §1, §4.1–4.5, §4.7, §5, §7 and §10.

**Out of scope:**

- Enclosure design and the DAC choice / mounting.
- GPIO changes (`src/`, `config/` untouched; `player.json` defaults hold).
- Soldering USB OTG to the Pi's test pads (the bottom zone gives the micro-USB port room).
- Display power switch, battery sense.

## Data model

### Nets

- `NETS` is unchanged, except that `PWR_KEY` and `GND` gain J7.1 / J7.2.
- The button board's `PWR_KEY` net loses SW1. Its J1 pin 8 becomes a no-connect.
- `CONFIG_NETS` and `BCM_TO_PIN` are unchanged, and `player.example.json` self-checks still pass.

### Display module (measured, "1.28" TFT VER1.0", GC9A01)

| | Value |
|---|---|
| Outline | 36 W × 45 H × 4 mm (round Ø36 + bottom tab 23 mm wide) |
| Header | 1×7 2.54 mm, pre-soldered, pins out the back |
| Pin row → module bottom edge | 2 mm |
| Pin row → screen center | 25 mm (pin 4 under the center) |
| Tab holes | 2 × ~Ø2.2 (M2), **19.2 mm** c-c, **3.5 mm** above the pin row |

### Carrier coordinates (front view, origin top-left, mm)

| Item | Position |
|---|---|
| Board | 65 × 45 |
| Display pin row (J5) | y = 43, pins centered on x = 32.5, pin 1 (VCC) at x = 40.12 |
| Display M2 holes | (22.9, 39.5), (42.1, 39.5) |
| Screen center | (32.5, 18) |
| Pi outline (back) | x 0–65, y 15–45 |
| Pi M2.5 holes | (3.5, 18.5), (61.5, 18.5), (3.5, 41.5), (61.5, 41.5) |
| J1 socket | centered x = 32.5, row centers 3.5 mm below the Pi's top edge (y ≈ 18.5). Pin 1 at the left end (Pi SD-card side) |
| Pi ports (bottom edge, from left) | mini-HDMI 12.4, **USB OTG 41.4**, PWR 54.0 |

Step 1 checks these against the official Pi Zero 2 W mechanical drawing. Pin 1 orientation is the critical item.

### Parts changes (`netlist.py` `PARTS`)

| Ref | Rev B | Rev C | Side | Height |
|---|---|---|---|---|
| J1 | IDC 2×20 horizontal | `Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical` | back | 8.5 mm |
| J5 | S7B-XH-A | `Connector_PinHeader_2.54mm:PinHeader_1x07_P2.54mm_Vertical` (holes for the module's header) | front | 6.5 mm (module) |
| J7 | — | `Connector_JST:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal` | back | 6.1 mm |
| H1–H4 | M2.5 inboard | M2.5 on the Pi pattern | — | — |
| H5–H6 | — | `MountingHole_2.2mm_M2` (display tab) | — | — |

All other parts are unchanged.

## Implementation plan

1. **Mechanics.**
   - Confirm the Pi Zero 2 W hole pattern, header position, port positions and antenna area from the official drawing.
   - Confirm the socket height (8.5) and the Pi top-side part heights under the carrier's back parts. Stop if any pair exceeds 10.5 mm.
2. **Netlist.** Add J7 and change the J1/J5 footprints in `PARTS`. Button board: drop SW1, J1.8 no-connect. Check: both `netlist.py` → `OK`.
3. **Schematics.** Rerun both `build_sch.py`. Check: ERC 0, exported netlist = `NETS`.
4. **Carrier placement.**
   - J5 + M2 holes + display outline on the front. J1 + Pi holes on the back, per the table above.
   - XH connectors at their edges, C1 flat, antenna keep-out.
   - Check: J1 pin 1 overlays Pi pin 1 in a Pi outline drawn on `User.Drawings`.
5. **Routing.** Same `Router` + GND pour (outside the keep-out). Check: DRC + parity 0/0/0.
6. **Silkscreen.** "Rev C", names, pin 1 markers, display + Pi outlines, micro-USB warning. Nothing under the display body on the front.
7. **Button board.** Set `GROUPS` / `BTN_PITCH`, regenerate. Check: length ≤ 101 mm, DRC 0/0/0.
8. **Fabrication.** `export-fab.ps1 -Board pcb` and `-Board buttons`.
9. **Docs.** READMEs and `docs/pcb-requirements.md` as listed in scope.

## Acceptance criteria

- [ ] Both `netlist.py` print `OK`. `NETS` diff vs Rev B = J7 only (plus SW1 removal on the button board).
- [ ] ERC 0 and DRC + parity 0/0/0 on both boards.
- [ ] Carrier is 65 × ~45. J1 is a 2×20 vertical socket on the back. J1 pin 1 matches Pi pin 1 with the Pi component side facing the carrier.
- [ ] The Pi M2.5 holes match the 58 × 23 pattern. With the Pi outline flush to the carrier's bottom edge, the ports are at that edge.
- [ ] J5 is on the front at y = 43, VCC rightmost from the front. The M2 holes are 19.2 c-c, 3.5 mm above the pin row.
- [ ] J7 PWR_BTN carries `PWR_KEY` / `GND`. J4 pinout is unchanged.
- [ ] Every back part + the Pi part under it ≤ 10.5 mm (README table).
- [ ] No copper pour over the antenna keep-out.
- [ ] Button board has 6 keys, length ≤ 101 mm, J1 pinout unchanged.
- [ ] Silkscreen shows "Rev C". "Rev B" appears nowhere on the carrier.
- [ ] Fab outputs are regenerated for both boards. The docs describe the Rev C stack and the portrait case.
- [ ] No change under `src/` or `config/`.

## Decisions

- **Yes:** Pi sandwiched under the carrier (HAT style). The user prefers a thicker player over a larger one. This reverses SPEC 24's "no sandwich" decision, which assumed a 17 mm target.
- **Yes:** display soldered to the carrier front. No cable, and the thinnest stack. **No:** a low-profile female socket (+2.5 mm). The trade-off is that swapping the display means desoldering it.
- **Yes:** 4000 mAh 6 × 60 × 91.5 cell. **No:** the 5000 mAh 4 × 59 × 134 cell, which needs a ~145 mm case.
- **Yes:** Pi ports flush with the carrier's bottom edge, with OTG into the open bottom zone. **No:** test-pad USB soldering (not needed with that room).
- **Yes:** POWER key moved to the top edge via new J7, with the 6-key strip at 9.6 mm pitch. **No:** a PH connector or shrinking gaps to keep 7 keys (still ~105 mm).
- **Yes:** J4 pinout frozen (pin 8 stays), so the existing XH-8 cable still works.

## Risks

| Risk | Mitigation |
|---|---|
| J1 is mirrored, so the Pi plugs in reversed (5 V onto GPIO). | Step 4 overlay check against the official drawing. Pin 1 is marked on both sides. Continuity check before first power. |
| The LiPo heats up behind the Pi. | 1 mm gap / insulating sheet. The SoC faces the carrier. Measure SoC and battery temperature under load at bring-up (battery < 45 °C). |
| Wi-Fi/BT gets weaker between the carrier copper and the battery. | Antenna keep-out on the carrier. Don't place the battery over the antenna end. Test range at bring-up. |
| Back parts collide with Pi parts or the micro-USB plug. | Step 1 height check. Keep the carrier back parts away from the Pi's bottom (port) edge. |
| The display pins protruding from the back touch the Pi. | Trim them to ≤ 2 mm after soldering. 11 mm gap. |
| The PWR micro-USB is reachable in the bottom zone (dual feed). | Silkscreen warning. Block the port in the enclosure. |
| The display can only be replaced by desoldering it. | Accepted (decision). |
