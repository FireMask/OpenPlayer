# SPEC 22 â€” Carrier PCB (bridge board) Rev A

> **Status:** Implemented
> **Depends on:** SPEC 05 (button GPIO), SPEC 17 (GC9A01 display), SPEC 20 (safe shutdown / `power_off`)
> **Date:** 2026-10-26
> **Objective:** Design a 2-layer KiCad carrier PCB that only bridges existing parts (FM5324GA charge/boost module 5 V output, panel power switch, Pi Zero 2 W via 40-pin ribbon, plug-in GC9A01 display, and an 8-pin button-board connector) and produce JLCPCB-ready Gerbers.

## Scope

**In:**

- KiCad 10 project in `hardware/pcb/` (`openplayer-carrier.kicad_pro`, `.kicad_sch`, `.kicad_pcb`). A project-local symbol/footprint library only where KiCad's stock libraries lack a part.
- Generator script `hardware/pcb/scripts/build_pcb.py` (KiCad's bundled Python). It places footprints, draws the outline from `BOARD_W` / `BOARD_H`, and routes tracks. Rerunning it reproduces the PCB.
- Schematic with these parts (all through-hole, hand-solderable):
  - **J1** â€” 2Ã—20 shrouded (keyed) 2.54 mm box header to the Pi via a 40-pin IDC ribbon. Uses both 5 V pins (2, 4) and every GND pin.
  - **J2** â€” `PWR_IN`, JST-XH 2-pin: 5V / GND from the charging module's `5V +` / `âˆ’` pads.
  - **J3** â€” `KEY`, JST-XH 2-pin: `K` / GND to the module's `K` pad.
  - **J4** â€” `BUTTONS`, JST-XH 8-pin: GND, PLAY, PREV, NEXT, VOL_UP, VOL_DOWN, MENU, KEY.
  - **J5** â€” `DISPLAY`, 1Ã—7 2.54 mm female header in module order VCC, GND, SCL, SDA, DC, CS, RST. The GC9A01 plugs in directly.
  - **J6** â€” `SWITCH`, JST-XH 2-pin to a panel-mount power switch (rocker/toggle â‰¥ 3 A) in series with 5V.
  - **C1** â€” 470â€“1000 ÂµF / 10 V electrolytic on 5V_SYS (optional populate). **C2** â€” 100 nF next to J1.
  - **TP1â€“TP3** â€” GND, 5V_SYS, 3V3 test points.
  - **H1â€“H4** â€” M2.5 mounting holes.
- GPIO mapping identical to `player.json` defaults (buttons 17/27/22/23/24/25, display DC 16 / RST 26, SPI0 CE0). No software change.
- Board 60 Ã— 45 mm, 2 layers, GND pour on both sides, JLCPCB default rules.
- Silkscreen: board name, "Rev A", connector names, pin 1, signal names on J4/J5, and "Do not use Pi micro-USB power while connected".
- ERC and DRC (with schematic parity) clean via `kicad-cli`.
- Fabrication output in `hardware/pcb/fabrication/`: Gerbers, drill files, BOM (CSV), generated with `kicad-cli`.
- Update `docs/pcb-requirements.md` and `docs/gpio-map.md` to match the chosen module and connectors (no M2 boost, J4 is 8-pin, battery straight to the module, J6 panel switch).

The battery and its JST connector go on the module's wires and never touch this PCB.

**Out of scope (for future specs):**

- Button board PCB (only its 8-pin connector pinout is fixed here).
- Ordering, assembly, and power bring-up tests (bring-up spec).
- Battery voltage sense / low-battery signal to the Pi.
- Panel VCC MOSFET switch for the display backlight.
- Enclosure design and final board dimensions.
- SMD assembly by JLCPCB.
- Any change to the battery or the charging module itself.

## Data model

### Nets

| Net | Connections |
|---|---|
| `5V_IN` | J2.1 â†’ J6.1 |
| `5V_SYS` | J6.2 â†’ J1.2, J1.4, C1+, C2, TP2 |
| `GND` | J1.6/9/14/20/25/30/34/39, J2.2, J3.2, J4.1, J5.2, C1âˆ’, C2, TP1 |
| `3V3` | J1.1, J1.17 â†’ J5.1, TP3 |
| `SPI_SCLK` | J1.23 â†’ J5.3 |
| `SPI_MOSI` | J1.19 â†’ J5.4 |
| `LCD_DC` | J1.36 â†’ J5.5 |
| `LCD_CS` | J1.24 â†’ J5.6 |
| `LCD_RST` | J1.37 â†’ J5.7 |
| `BTN_PLAY` | J1.11 â†’ J4.2 |
| `BTN_PREV` | J1.13 â†’ J4.3 |
| `BTN_NEXT` | J1.15 â†’ J4.4 |
| `BTN_VOLUP` | J1.16 â†’ J4.5 |
| `BTN_VOLDN` | J1.18 â†’ J4.6 |
| `BTN_MENU` | J1.22 â†’ J4.7 |
| `PWR_KEY` | J4.8 â†’ J3.1 (not a Pi GPIO) |

J1 pin N = Pi physical pin N (straight-through IDC ribbon, key aligned). Unused J1 pins get no-connect flags in the schematic.

### Footprints (KiCad stock libraries)

| Ref | Footprint |
|---|---|
| J1 | `Connector_IDC:IDC-Header_2x20_P2.54mm_Vertical` |
| J2, J3, J6 | `Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical` |
| J4 | `Connector_JST:JST_XH_B8B-XH-A_1x08_P2.50mm_Vertical` |
| J5 | `Connector_PinSocket_2.54mm:PinSocket_1x07_P2.54mm_Vertical` |
| C1 | `Capacitor_THT:CP_Radial_D10.0mm_P5.00mm` |
| C2 | `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` |
| TP1â€“3 | `TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm` |
| H1â€“4 | `MountingHole:MountingHole_2.7mm_M2.5` |

### `build_pcb.py` parameters

```python
BOARD_W = 60.0      # mm; the 2Ã—20 header (~56 mm) sets the minimum
BOARD_H = 45.0      # mm
HOLE_INSET = 3.5    # mm from each edge to mounting-hole center
POWER_TRACK = 1.0   # mm, 5V_IN / 5V_SYS / GND
SIGNAL_TRACK = 0.25 # mm, everything else
CLEARANCE = 0.2     # mm (JLCPCB 2-layer default allows 0.127)
```

## Implementation plan

1. **Docs.** Update `docs/pcb-requirements.md` (charging module = FM5324GA board with 5 V out, no M2, battery straight to module, J4 8-pin with `PWR_KEY`, J6 panel switch, ribbon to Pi) and `docs/gpio-map.md` (J4/J5 pinout, `PWR_KEY` is not a GPIO). No code.
2. **Single source of truth.** Create `hardware/pcb/scripts/netlist.py` with the parts table (ref, value, symbol, footprint) and the net table from the Data model. A `__main__` self-check asserts that button and DC/RST pins match `config/player.example.json` and that no J1 pin is in two nets. Run `python hardware/pcb/scripts/netlist.py` â†’ `OK`.
3. **Schematic.** `hardware/pcb/scripts/build_sch.py` (plain Python) writes `openplayer-carrier.kicad_sch`, embedding stock symbols copied from KiCad's `.kicad_sym` libraries. Connections use net labels on each pin; unused J1 pins get no-connect flags. It also writes `openplayer-carrier.kicad_pro`. Check: `kicad-cli sch erc` â†’ 0 errors, and the file opens in KiCad.
4. **Placement.** `hardware/pcb/scripts/build_pcb.py` (KiCad's bundled Python, `pcbnew`) creates `openplayer-carrier.kicad_pcb`:
   - outline from `BOARD_W` Ã— `BOARD_H`; H1â€“H4 at `HOLE_INSET`;
   - J5 on the front (display faces the enclosure front);
   - J1, J2, J3, J4, J6, C1 on the back, cable connectors on the edges facing outward;
   - nets assigned from `netlist.py`; silkscreen per the Scope.

   Check: opens in KiCad, and DRC shows only "unconnected" items.
5. **Routing.** Extend `build_pcb.py`: power tracks at `POWER_TRACK`, signals at `SIGNAL_TRACK`, GND pour on both layers, stitching vias, SPI kept away from the 5V entry. Check: `kicad-cli pcb drc --schematic-parity` â†’ 0 errors, 0 unconnected.
6. **Fabrication.** `hardware/pcb/scripts/export-fab.ps1` runs `kicad-cli` to write Gerbers + drill (zipped for JLCPCB), BOM CSV, and top/bottom 3D renders (`render-top.png`, `render-bottom.png`) into `hardware/pcb/fabrication/`.
7. **README.** `hardware/pcb/README.md`: how to regenerate (`netlist.py` â†’ `build_sch.py` â†’ `build_pcb.py` â†’ `export-fab.ps1`), how to resize the board, connector pinout table, and the ribbon/micro-USB warning.

## Acceptance criteria

- [x] `python hardware/pcb/scripts/netlist.py` prints `OK`; changing a button pin in the table makes it fail.
- [x] `build_sch.py` and `build_pcb.py` regenerate the `.kicad_sch` and `.kicad_pcb` from scratch without manual edits.
- [x] `kicad-cli sch erc` reports 0 errors.
- [x] `kicad-cli pcb drc --schematic-parity` reports 0 errors, 0 unconnected items, and 0 parity issues.
- [x] Board outline is `BOARD_W` Ã— `BOARD_H` (60 Ã— 45 mm) with 4 M2.5 holes. Changing both values and rerunning `build_pcb.py` gives a board that still passes DRC (tested with at least one other size).
- [x] Every net in the Data model table exists with exactly the listed pins (checked against the netlist from `kicad-cli sch export netlist`).
- [x] 5V_IN, 5V_SYS, and GND tracks are â‰¥ 1.0 mm; signal tracks are â‰¥ 0.25 mm.
- [x] J1 uses both 5 V pins (2, 4) and all 8 GND pins.
- [x] J5 is on the front; J1, J2, J3, J4, J6 are on the back.
- [x] Silkscreen shows board name, "Rev A", every connector name, pin 1 markers, J4/J5 signal names, and the micro-USB warning.
- [x] `export-fab.ps1` produces a Gerber + drill zip, a BOM CSV, and two PNG renders in `hardware/pcb/fabrication/`.
- [x] The Gerber zip loads in JLCPCB's online viewer without errors (manual check).
- [x] `docs/pcb-requirements.md` and `docs/gpio-map.md` match the J4 8-pin pinout, J6, and the FM5324GA module.
- [x] No file under `src/` or `config/` changes.

## Decisions

- **Yes:** FM5324GA USB-C charge/boost board (DWEII, Amazon MX B09YD5C9QC). One module gives charging, power-path and regulated 5 V / 2 A; the PCB stays a pure bridge.
- **No:** Steren ARD-343 (TP4056 type). Battery-voltage output only, no power-path, 2 A trip limit too close to the Pi's peak draw at low battery.
- **No:** separate boost module (M2). The module already outputs 5 V.
- **Yes:** battery wired straight to the module. The PCB never carries raw battery current.
- **Yes:** Pi powered through header pins 2 and 4. No micro-USB cable; the silkscreen warns not to use both.
- **Yes:** Pi beside the board on a 40-pin IDC ribbon. Keyed, standard, removable. Voltage drop over the ribbon is checked at bring-up.
- **No:** partial cable with only the used pins. Error-prone and not keyed.
- **Yes:** display plugs directly into a 7-pin female header on the PCB.
- **Yes:** buttons on a separate board via 8-pin JST-XH (6 GPIO + `PWR_KEY` + GND). Every button outside the enclosure comes through one connector.
- **Yes:** `PWR_KEY` goes only to the module's `K` pad, not to a Pi GPIO. Power-on works with the Pi off.
- **Yes:** panel-mount power switch through J6. Board-mounted slide switches are rated 100â€“500 mA; a â‰¥ 3 A rocker on the enclosure is cheap and easy to source.
- **No:** board-mounted slide switch (SW1). Under-rated, and ties the board position to the enclosure.
- **Yes:** optional bulk capacitor C1 on 5V_SYS. Absorbs a possible output dropout when the charger is plugged in; populate after testing.
- **Yes:** JST-XH (2.5 mm, 3 A) for cable connectors. Polarized; one family for everything.
- **Yes:** all through-hole, hand-soldered. No JLCPCB assembly for a board this simple.
- **Yes:** PCB generated by scripts (`netlist.py` as single source of truth â†’ `build_sch.py` / `build_pcb.py`). Resizing or changing a pin means rerunning, not redrawing.
- **No:** Freerouting autorouter. Needs Java; with ~25 nets, scripted routing is enough.
- **Yes:** board 60 Ã— 45 mm as a parameter. The 2Ã—20 header (~56 mm) forces the width; final size depends on the enclosure.
- **No:** battery voltage sense, panel VCC MOSFET, button board PCB. Each one is its own spec.

## Risks

| Risk | Mitigation |
|---|---|
| Module output drops when the charger is plugged in, resetting the Pi. | C1 footprint (470â€“1000 ÂµF). Test at bring-up; if it still resets, it goes in a power-path spec. |
| Module doesn't auto-shut off with the Pi halted (> 50 mA) and drains the battery. | J6 switch cuts 5 V. Measure halted current at bring-up. |
| Voltage drop over the ribbon at high load (thin wires). | Both 5 V pins and 8 GNDs, short ribbon (â‰¤ 10 cm). Measure 5 V at the Pi under load; must be â‰¥ 4.75 V. |
| Ribbon plugged in reversed. | Shrouded/keyed J1 and keyed IDC ribbon; pin-1 marker on silkscreen. |
| Pi powered from micro-USB with the board connected (dual feed). | Silkscreen warning; documented in README and `pcb-requirements.md`. |
| Scripted routing is DRC-clean but ugly or fragile. | Review 3D renders and the KiCad layout before ordering; manual fixes allowed as long as DRC parity stays clean. |
| Module pad spacing/size unmeasured. | Doesn't affect the PCB: the module connects by wires to J2/J3. |
| GC9A01 module header pitch or order differs from the one on hand. | J5 uses the order validated in SPEC 17; verify against the physical module before ordering. |

## What is **not** in this spec

- Button board PCB.
- Ordering, assembly, and power bring-up tests.
- Battery voltage sense / low-battery signal.
- Panel VCC MOSFET for the display backlight.
- Enclosure and final board dimensions.
- SMD assembly.
- Changes to the battery or charging module.

Each one, if it lands, goes in its own spec.
