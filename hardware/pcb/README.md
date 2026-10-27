# OpenPlayer carrier PCB — Rev C

Bridge board (SPEC 22, thin Rev B in SPEC 24, Pi sandwich in SPEC 25): connectors only, no active parts. The Pi Zero 2 W plugs into J1 on the back like a HAT, the GC9A01 module is soldered on the front, and the button board, the FM5324GA charge/boost module, the panel power switch and the POWER key connect by cable. Requirements: `docs/pcb-requirements.md`.

Rev A (display plugged on the front, Pi on a ribbon) and Rev B (single-sided, Pi on a ribbon) are in git history only.

![top](fabrication/render-top.png)
![bottom](fabrication/render-bottom.png)

> **Never plug power into the Pi's micro-USB PWR port while it sits on the carrier.** The board feeds the Pi through header pins 2 and 4. Block that port in the enclosure.

## Regenerate

Every KiCad file is generated. Do not edit `.kicad_sch` / `.kicad_pcb` / `.kicad_dru` by hand: change the scripts and rerun.

```powershell
python hardware\pcb\scripts\netlist.py        # self-check against config/player.example.json → OK
python hardware\pcb\scripts\build_sch.py      # → openplayer-carrier.kicad_sch
& "C:\Program Files\KiCad\10.0\bin\python.exe" hardware\pcb\scripts\build_pcb.py   # → .kicad_pcb (placed + routed) + .kicad_dru
.\hardware\common\export-fab.ps1 -Board pcb   # ERC + DRC, then Gerbers, drill, BOM, renders → fabrication/
```

| File | Role |
|---|---|
| `scripts/netlist.py` | Single source of truth: parts, footprints and nets |
| `scripts/build_sch.py` | Writes the schematic (stock KiCad 10 symbols, net labels per pin) |
| `scripts/build_pcb.py` | Outline, placement, Pi / display geometry, silkscreen, keep-outs, routing (grid router), GND pours |
| `../common/pcbgen.py` | Generator code shared with the button board: schematic writer, placement, grid router, GND pour |
| `../common/export-fab.ps1` | Fabrication package for any board (`-Board pcb`); refuses to export on any ERC/DRC finding |

- **Change a pin:** edit `NETS` in `netlist.py`. If it is a GPIO, change `config/player.example.json` too; the self-check fails until both agree.
- **Size:** 65 × 53 mm (`BOARD_W` / `BOARD_H` in `build_pcb.py`). The width is the Pi's. The height is the Pi (30) plus the band above it, which J4 (23.5 mm long) needs on the right edge: the Pi's mounting holes leave only 17 mm of edge between them.
- **Pi pin 1 check:** `build_pcb.py` asserts that every J1 pad lands on the Pi header pin of the same number (official Pi Zero 2 W drawing), and draws the Pi outline and pin 1 on `User.Drawings`.
- `openplayer-carrier.kicad_dru` waives courtyard clearance only between J5 and the display holes H5/H6: they sit 3.5 mm from the header, under the module's own tab.
- Order at JLCPCB with `fabrication/openplayer-carrier-gerbers.zip` (2 layers, 1.6 mm, defaults).

## Layout

Seen from the front (the display side). The Pi sits behind the lower 30 mm, ports flush with the bottom edge.

```
            ↑ J7 PWR_BTN
       ┌─────[J7]──────────────────────┐
 ← J2  │                          J4   │ →
 ← J6  │      C1  C2  TPs         BUT- │ →  button strip (right wall)
       ├ H1 ════════ J1 PI ═══════ H2 ┤  ← Pi top edge (Pi behind, y 23–53)
 ← J3  │          display (front)      │
       │      Ø36, centered at y 26    │
       │ H3     H5 ─[ J5 ]─ H6     H4 │
       └───────────────────────────────┘
         Pi ports ↓: mini-HDMI 12.4, USB OTG 41.4, PWR 54.0 mm from the left
```

| Item | Position (mm, front view, origin top-left) |
|---|---|
| Pi outline (back) | x 0–65, y 23–53 |
| Pi M2.5 holes H1–H4 | (3.5, 26.5), (61.5, 26.5), (3.5, 49.5), (61.5, 49.5): 58 × 23 |
| J1 pin 1 | (8.37, 27.77): left end, inner row; pin 2 on the edge row above it |
| J5 pin row | y = 51, pin 1 (VCC, square) rightmost at x = 40.12 |
| Display M2 holes H5/H6 | (22.9, 47.5), (42.1, 47.5): 19.2 c-c, 3.5 mm above the pin row |
| Screen center | (32.5, 26) |
| Antenna keep-out | x 18–37, y 46–53: no copper pour on either layer (pads and tracks may cross) |

## Stack

Front to back, inside a ≈ 80 × 110 × 33 mm portrait case:

| Layer | mm |
|---|---:|
| Display module (4) on its header spacer (2.5) | 6.5 |
| Carrier | 1.6 |
| Gap: J1 socket (8.5) + Pi header plastic (2.5); 11 mm M2.5 standoffs on H1–H4 | 11 |
| Pi Zero 2 W, component side toward the carrier | ~2.2 |
| Gap / insulating sheet | 1 |
| 4000 mAh LiPo, 6 × 60 × 91.5 | 6 |
| **Total** | **~28.3** |

- The display's header is soldered on the back; trim its pins to ≤ 2 mm.
- The J1, C1, C2, TP and XH leads that come through the front sit under the display (2.5 mm gap): trim them flush.
- H5/H6 take 2.5 mm M2 standoffs under the module's tab; the screws go in from the back.

## Connectors and heights

Every cable connector is on the back, mouth at the edge. Pin 1 is marked on the silkscreen. J4 pin names are printed on the front, right of the display; J5 pin names on the back, by the solder joints.

Height rule: part height + Pi part under it ≤ 10.5 mm (the 11 mm gap minus 0.5 mm air). Part heights are from KiCad's 3D models; Pi part heights are typical datasheet values (mini-HDMI ≈ 3.2, micro-USB ≈ 2.7, microSD / CSI / SoC ≤ 1.5): measure at bring-up.

| Ref | Name | Part | Edge, wire direction | Height | Pi part under it | Sum | Pins |
|---|---|---|---|---:|---|---:|---|
| J1 | PI | 2×20 female socket, 2.54 mm, vertical, 8.5 mm (`PinSocket_2x20_P2.54mm_Vertical`) | — (Pi plugs in) | 8.5 | header plastic 2.5 | 11 (the gap) | J1 pin N = Pi pin N |
| J2 | PWR_IN | JST-XH 2 side entry, S2B-XH-A | left, top | 6.1 | none (above the Pi) | 6.1 | 1 5V (module `5V +`), 2 GND (module `−`) |
| J6 | SWITCH | JST-XH 2 side entry, S2B-XH-A, to a ≥ 3 A panel switch | left, top | 6.1 | none | 6.1 | 1 5V_IN, 2 5V_SYS |
| J3 | KEY | JST-XH 2 side entry, S2B-XH-A | left, middle | 6.1 | microSD ≈ 1.3 | 7.4 | 1 PWR_KEY (module `K`), 2 GND |
| J4 | BUTTONS | JST-XH 8 side entry, S8B-XH-A | right, top | 6.1 | none | 6.1 | 1 GND, 2 PLAY (GPIO17), 3 PREV (GPIO27), 4 NEXT (GPIO22), 5 VOL+ (GPIO23), 6 VOL− (GPIO24), 7 MENU (GPIO25), 8 PWR_KEY |
| J7 | PWR_BTN | JST-XH 2 side entry, S2B-XH-A, to a panel momentary key | top, up | 6.1 | none | 6.1 | 1 PWR_KEY, 2 GND |
| J5 | DISPLAY | holes for the module's pre-soldered 1×7 2.54 mm header (`PinHeader_1x07_P2.54mm_Vertical`); nothing to buy | — | pins ≤ 2 (trimmed) | micro-USB OTG ≈ 2.7 | 4.7 | 1 VCC 3V3, 2 GND, 3 SCL (GPIO11), 4 SDA (GPIO10), 5 DC (GPIO16), 6 CS (GPIO8/CE0), 7 RST (GPIO26) |
| C1 | — | 470 µF / 10 V, Ø8 mm radial, **lying flat** | — | ≈ 8 | none | 8 | optional |
| C2 | — | 100 nF disc, standing | — | ≤ 7.5 | none | 7.5 | — |
| TP1–3 | GND / 5V / 3V3 | THT test pads | — | ~0 | none | ~0 | — |
| H5/H6 | — | M2 screw heads | — | ≈ 1.6 | micro-USB OTG ≈ 2.7 | 4.3 | — |

- C1 and C2 sit above the Pi, never over its ports (they would exceed 10.5 mm there).
- `PWR_KEY` goes to the module's `K` pad (J3), the POWER key (J7) and J4 pin 8. It is not a Pi GPIO. The 6-key button board leaves J4 pin 8 unconnected; the pin stays so the XH-8 cable is unchanged.
- The battery connects straight to the module, never to this board.
- C1 is optional: populate it if the Pi resets when USB-C is plugged in. Bend its leads 90° so the body lies inside the silkscreen outline, with `+` on the marked pad. The outlined area is a keep-out for other parts.
- Test points: TP1 GND, TP2 5V_SYS, TP3 3V3.

## Cables

| Cable | Ends | Wiring |
|---|---|---|
| Buttons | J4 XH-8 → button board J1 XH-8 | Straight, pin 1 → pin 1 (`hardware/buttons/README.md`) |
| POWER key | J7 XH-2 → panel momentary key on the case's top edge | Either way round (key shorts PWR_KEY to GND) |
| Power | J2 / J3 → module `5V +` `−` / `K`; J6 → panel switch | XH-2 pigtails, short |

Check every cable pin by pin with a meter before connecting.

## Bring-up

See the checklist in `docs/pcb-requirements.md` §9. Power up first without the Pi, check 5 V at TP2 with the switch on and 0 V with it off. Before plugging the Pi in, check with a meter that J1 pins 2 and 4 carry 5 V and no other J1 pin does, and that the Pi goes on component side toward the carrier, its ports at the bottom edge.

- Measure SoC and battery temperature under load (battery < 45 °C).
- Test Wi-Fi/BT range: the antenna sits between the carrier and the battery.
