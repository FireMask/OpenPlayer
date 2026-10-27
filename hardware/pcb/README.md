# OpenPlayer carrier PCB — Rev B

Bridge board (SPEC 22, reworked thin in SPEC 24): connectors only, no active parts. It joins the Pi Zero 2 W (via a 40-pin IDC ribbon), the GC9A01 display (on a cable), the button board, the FM5324GA charge/boost module and a panel power switch. Requirements: `docs/pcb-requirements.md`.

Rev B is single-sided (every part on the back, the front is flat) and ≤ 11 mm thick: 1.6 mm board + ≤ 9.5 mm of parts. Every connector enters from a board edge, so the wires run parallel to the board. Rev A (60 × 45, vertical connectors, display plugged on the front) is in git history only.

![top](fabrication/render-top.png)
![bottom](fabrication/render-bottom.png)

> **Never plug power into the Pi's micro-USB port while the ribbon is connected.** The board feeds the Pi through header pins 2 and 4.

## Regenerate

Every KiCad file is generated. Do not edit `.kicad_sch` / `.kicad_pcb` by hand: change the scripts and rerun.

```powershell
python hardware\pcb\scripts\netlist.py        # self-check against config/player.example.json → OK
python hardware\pcb\scripts\build_sch.py      # → openplayer-carrier.kicad_sch
& "C:\Program Files\KiCad\10.0\bin\python.exe" hardware\pcb\scripts\build_pcb.py   # → .kicad_pcb (placed + routed)
.\hardware\common\export-fab.ps1 -Board pcb   # ERC + DRC, then Gerbers, drill, BOM, renders → fabrication/
```

| File | Role |
|---|---|
| `scripts/netlist.py` | Single source of truth: parts, footprints and nets |
| `scripts/build_sch.py` | Writes the schematic (stock KiCad 10 symbols, net labels per pin) |
| `scripts/build_pcb.py` | Outline, placement, silkscreen, C1 keep-out, routing (grid router), GND pours |
| `../common/pcbgen.py` | Generator code shared with the button board: schematic writer, placement, grid router, GND pour |
| `../common/export-fab.ps1` | Fabrication package for any board (`-Board pcb`); refuses to export on any ERC/DRC finding |

- **Change a pin:** edit `NETS` in `netlist.py`. If it is a GPIO, change `config/player.example.json` too; the self-check fails until both agree.
- **Size:** 60 × 41.5 mm (`BOARD_W` / `BOARD_H` in `build_pcb.py`). That is the minimum: J1's 2 × 20 row sets the width, J1 plus the three stacked XH-2 set the height. Placement is anchored to the edges, so a larger board still places; rerun and check DRC.
- Order at JLCPCB with `fabrication/openplayer-carrier-gerbers.zip` (2 layers, 1.6 mm, defaults).

## Layout

Seen from the front (the flat side); the parts are on the back.

```
        ┌────────────[ J5 DISPLAY ]────────────┐   ↑ display cable
 ← J2  │ PWR_IN   H1                 H2   J4   │ →
 ← J6  │ SWITCH  C2    C1 (flat)     TPs  BUT- │ →  button strip
 ← J3  │ KEY      H3                 H4   TONS │ →
        ├──────────────[ J1  PI ]──────────────┤
        └──────────────────────────────────────┘   ↓ ribbon to the Pi
```

## Connectors and heights

All on the back, mouth at the edge. Pin 1 is marked on the silkscreen; J4/J5 pin names are printed on the front, behind the pins. Heights are above the board, measured from KiCad's 3D models of each part (the budget is 9.5 mm).

| Ref | Name | Part | Edge, wire direction | Height | Pins |
|---|---|---|---|---:|---|
| J1 | PI | 2×20 shrouded IDC, right-angle (`IDC-Header_2x20_P2.54mm_Horizontal`) | bottom, down | ≈ 9.1 mm | J1 pin N = Pi pin N, straight ribbon |
| J2 | PWR_IN | JST-XH 2 side entry, S2B-XH-A | left, upper | 6.1 mm | 1 5V (module `5V +`), 2 GND (module `−`) |
| J6 | SWITCH | JST-XH 2 side entry, S2B-XH-A, to a ≥ 3 A panel switch | left, middle | 6.1 mm | 1 5V_IN, 2 5V_SYS |
| J3 | KEY | JST-XH 2 side entry, S2B-XH-A | left, lower | 6.1 mm | 1 PWR_KEY (module `K`), 2 GND |
| J4 | BUTTONS | JST-XH 8 side entry, S8B-XH-A | right, upper | 6.1 mm | 1 GND, 2 PLAY (GPIO17), 3 PREV (GPIO27), 4 NEXT (GPIO22), 5 VOL+ (GPIO23), 6 VOL− (GPIO24), 7 MENU (GPIO25), 8 PWR_KEY |
| J5 | DISPLAY | JST-XH 7 side entry, S7B-XH-A | top center, up | 6.1 mm | 1 VCC 3V3, 2 GND, 3 SCL (GPIO11), 4 SDA (GPIO10), 5 DC (GPIO16), 6 CS (GPIO8/CE0), 7 RST (GPIO26) |
| C1 | — | 470 µF / 10 V, Ø8 mm radial, **lying flat** | — | ≈ 8 mm | optional |
| C2 | — | 100 nF disc, standing | — | ≤ 7.5 mm | — |
| TP1–3 | GND / 5V / 3V3 | THT test pads | — | ~0 | — |

- `PWR_KEY` goes only to the module's `K` pad; it is not a Pi GPIO.
- The battery connects straight to the module, never to this board.
- C1 is optional: populate it if the Pi resets when USB-C is plugged in. Bend its leads 90° so the body lies inside the silkscreen outline, with `+` on the marked pad. The outlined area is a keep-out for other parts.
- Test points: TP1 GND, TP2 5V_SYS, TP3 3V3.

## Cables

| Cable | Ends | Wiring |
|---|---|---|
| Display | J5 XH-7 → 1 × 7 Dupont female housing on the GC9A01's male pins | **Straight:** J5 pin N → module pin N (VCC, GND, SCL, SDA, DC, CS, RST). Keep it short (SPI); if the image shows artifacts, lower the SPI clock in `player.json`. |
| Buttons | J4 XH-8 → button board J1 XH-8 | Straight, pin 1 → pin 1 (`hardware/buttons/README.md`) |
| Pi | J1 → Pi header, 40-pin IDC ribbon ≤ 10 cm | Straight-through; keyed socket |
| Power | J2 / J3 → module `5V +` `−` / `K`; J6 → panel switch | XH-2 pigtails, short |

Check every cable pin by pin with a meter before connecting.

## Bring-up

See the checklist in `docs/pcb-requirements.md` §9. Power up first without the Pi, check 5 V at TP2 with the switch on and 0 V with it off, and only then connect the ribbon.
