# OpenPlayer PCB Rev A — Project Requirements

**Document type:** Hardware requirements and design brief  
**Status:** Draft for schematic development  
**Target CAD:** KiCad  
**Target manufacturer:** JLCPCB  
**Main controller:** Raspberry Pi Zero 2 W  
**Display:** 1.28-inch round TFT, GC9A01, 240 × 240, SPI  
**Battery concept:** Single-cell Li-ion/LiPo, nominal 3.7 V, planned capacity 5000 mAh  
**Revision:** A

---

## 1. Project goal

Design a custom printed circuit board (PCB) for a portable, modular DIY MP3 player named **OpenPlayer**. The current prototype works at a basic level on a Raspberry Pi Zero 2 W. The PCB should replace loose prototype wiring with reliable, labeled, serviceable connectors for:

- Raspberry Pi Zero 2 W, installed using a removable 40-pin header.
- Six physical control buttons mounted on a separate button module.
- A 1.28-inch round GC9A01 240 × 240 SPI TFT display ("1.28 TFT ver 1.0", 7-pin header, no backlight pin), currently wired with dupont jumpers.
- A single-cell rechargeable Li-ion/LiPo battery.
- A replaceable charging/power-management module that supports safe simultaneous operation and charging (power-path).
- A regulated supply for the Raspberry Pi.

The design should prioritize modularity, safe battery handling, stable power, ease of assembly, and future repairability.

## 2. Existing software and system architecture

The PCB is hardware interconnect and power distribution; it is not intended to replace the Raspberry Pi or run application software itself.

The Raspberry Pi Zero 2 W will continue running Raspberry Pi OS and the existing MP3-player software architecture:

- MPD as the playback engine and source of playback state.
- A central C#/.NET service for player logic.
- A Python GPIO hardware agent for physical button input and display rendering (pins configurable in `player.json`; defaults below).
- SSH for administration.
- SPI display control for the GC9A01.
- Existing USB DAC for audio output.
- Bluetooth headphone output is a desired capability of the software/system, not a PCB audio codec requirement.

Do not move the project to an ESP32 as part of this PCB revision.

## 3. Design principles

1. **Modular:** the Pi, battery, charging module, display, and button module should be replaceable without reworking the entire PCB.
2. **Safe power design:** no direct connection from a Li-ion cell to the Pi's 5 V supply input.
3. **Power-path:** charging should be possible while the player is operating, with proper load sharing and no unsafe charging behavior.
4. **Stable 5 V rail:** supply the Pi through an appropriate connector with sufficient current capacity and low voltage drop.
5. **Serviceable:** use keyed/polarized connectors where practical, clear silkscreen labels, mounting holes, and test points.
6. **KiCad source-first:** keep editable schematic and PCB source files under version control.
7. **Fabrication-ready:** produce checked Gerbers and drill files for JLCPCB only after ERC/DRC and physical review.
8. **Do not assume module pinouts:** verify each purchased module's exact pin labels, connector pitch, voltage limits, and datasheet before finalizing footprints.

## 4. Functional blocks

### 4.1 Raspberry Pi connection

- Provide a 2 × 20, 2.54 mm pitch header footprint compatible with the Raspberry Pi Zero 2 W.
- Prefer a removable header/socket arrangement rather than permanently soldering the Pi to the carrier board.
- Verify the physical board outline, mounting holes, header orientation, and connector clearance against the official Pi mechanical dimensions.
- Avoid routing the board's regulated power into multiple Pi power inputs simultaneously.
- Preferred power entry is the Pi's dedicated micro-USB power connector using an appropriate cable/adapter, unless a carefully reviewed alternative is selected.

### 4.2 Display connector J3

Display: GC9A01, 1.28-inch round TFT, 240 × 240, SPI.

7-position interface, in the module's silkscreen order. Matches the validated prototype wiring (`docs/gpio-map.md` §10) and `player.json` defaults (`hardware.display.dc` = 16, `rst` = 26):

| J3 pin | Module label | Signal | Raspberry Pi BCM GPIO | Pi physical pin |
|---:|---|---|---:|---:|
| 1 | VCC | 3V3 | — | 17 (or 1) |
| 2 | GND | GND | — | 34 (any GND) |
| 3 | SCL | SPI0 SCLK | GPIO11 | 23 |
| 4 | SDA | SPI0 MOSI | GPIO10 | 19 |
| 5 | DC | Data/command | GPIO16 | 36 |
| 6 | CS | SPI0 CE0 | GPIO8 | 24 |
| 7 | RST | Reset | GPIO26 | 37 |

Important:
- SDA/SCL on this module are SPI data/clock, not I²C.
- VCC and logic are 3.3 V only; never 5 V.
- The module has no backlight (BL) pin: the backlight is on whenever VCC is present, including after the Pi shuts down (the Pi keeps 3.3 V while powered). Consider an optional high-side switch (P-MOSFET) on the panel VCC, controlled by a free GPIO, so the panel can be fully powered off; otherwise rely on the hard power switch (§11 item 9).
- DC/RST were moved from GPIO5/GPIO6 (pins 29/31) to GPIO16/GPIO26 (pins 36/37) after a short between adjacent header pins 29–31 on the prototype. Do not revert without updating `player.json` defaults.
- SPI0 is in use, so GPIO7–11 are not free for other functions.
- Header pitch on the module is 2.54 mm; still verify the exact module before finalizing the footprint.

### 4.3 Button module connector J4

Use one 7-pin connector for a separate module containing six normally-open momentary buttons and a shared ground.

| J4 pin | Signal | Raspberry Pi BCM GPIO | Pi physical pin |
|---:|---|---:|---:|
| 1 | GND common | — | GND |
| 2 | PLAY / PAUSE | GPIO17 | 11 |
| 3 | PREVIOUS | GPIO27 | 13 |
| 4 | NEXT | GPIO22 | 15 |
| 5 | VOL_UP | GPIO23 | 16 |
| 6 | VOL_DOWN | GPIO24 | 18 |
| 7 | MENU | GPIO25 | 22 |

Pin assignment matches `player.json` defaults and `docs/gpio-map.md`.

Button behavior:
- Each normally-open button connects its signal line to GND while pressed.
- Configure the GPIO as input with internal pull-up in software.
- No external resistor per button is required for the basic design.
- Provide clear silkscreen names and pin-1 marking.
- Use a polarized connector if possible.
- Confirm connector pitch, current rating (signal-level current only), and cable strain relief.

### 4.4 Battery and charging

- Battery concept: one Li-ion/LiPo cell, 3.7 V nominal, planned 5000 mAh.
- A 1S cell voltage is typically around 4.2 V when fully charged; actual operating limits must follow the exact cell datasheet.
- Provide a polarized two-pin battery connector J1, with clearly marked BAT+ and BAT−.
- Choose connector family and wire gauge based on the expected maximum battery current, not only on physical size.
- The battery pack must have suitable protection, either built into the pack or implemented in a properly designed protection circuit.
- Do not connect the cell directly to the Pi's 5 V rail.
- Charging module M1 must explicitly support a single-cell battery and power-path/load-sharing operation while the system is running.
- The module must have separate, clearly documented battery, input, and system/output connections.
- The basic TP4056-only charger module is not an acceptable default for this use case because it does not by itself provide the required power-path behavior.
- USB-C charging input should be on the replaceable module M1 unless there is a clear reason to put it on the carrier PCB.
- Confirm charge current is appropriate for the exact battery and thermal design.
- Verify behavior during boot, high load, low battery, and unplugging/plugging USB power.

### 4.5 Regulated supply

- The Raspberry Pi needs a stable 5 V supply; a design target around 5.1 V may be evaluated, but must remain within the Pi's accepted input range and be verified under load.
- The power converter must support the actual system load and transient peaks. A nominal capability around 5 V / 3 A is an initial sizing target to investigate, not a guaranteed final specification.
- Check the converter's output rating at the actual battery input voltage, thermal conditions, and required input current.
- The boost converter M2 may be separate from M1 unless a suitable integrated module is found.
- First determine whether M1's system output is raw battery voltage or regulated voltage; do not connect M2 until this is known.
- Use wide/short power traces, appropriate copper width, good grounding, input/output capacitors per the selected converter datasheet, and thermal clearance.
- Provide test points for GND, 3V3, and regulated 5 V.
- Avoid powering the Pi simultaneously through two independent 5 V paths unless the power architecture explicitly isolates and manages them.

### 4.6 Power connector J2

- Provide a connector or cable interface for regulated 5 V and GND to the Pi.
- Preferred initial approach: power the Pi through its dedicated micro-USB power connector via a suitable cable/adapter.
- If instead using the 40-pin header's 5 V pins, the design must explicitly address back-powering, USB power interaction, protection, and safe source selection. Do not connect both routes without a reviewed power architecture.

### 4.7 Expansion and future additions

- Reserve optional space or an unpopulated connector for future low-speed modules if board area permits.
- Keep GPIO2/GPIO3 available for potential I²C devices.
- OLED is not part of this revision; the current screen target is the GC9A01 TFT.
- Do not add an audio DAC to this PCB by default; the current prototype uses an existing USB DAC.

## 5. Proposed connector list

These are functional references, not final footprints.

| Ref. | Function | Initial pin count | Notes |
|---|---|---:|---|
| H1 | Raspberry Pi 40-pin header/socket | 40 | 2 × 20, 2.54 mm pitch; removable Pi connection |
| J1 | Battery | 2 | Polarized, rated for expected current |
| J2 | Pi power | 2 | Regulated 5 V and GND, exact implementation to be reviewed |
| J3 | GC9A01 display | 7 | VCC, GND, SCL, SDA, DC, CS, RST; no BL pin |
| J4 | Button module | 7 | Six GPIO signals plus common GND |
| J5 | Charging input | On M1 or optional | Prefer USB-C on replaceable charging module |
| TP1 | GND | 1 test point | Accessible |
| TP2 | 3V3 | 1 test point | Accessible |
| TP3 | 5V_SYS | 1 test point | Accessible |
| M1 | Charging/power-path module | Module-specific | Replaceable |
| M2 | Boost converter | Module-specific | Replaceable unless integrated into M1 |

## 6. GPIO conflict review

The proposed assignments do not overlap between the six buttons and display signals:

| Function | BCM GPIO | Physical pin |
|---|---:|---:|
| Display MOSI | 10 | 19 |
| Display SCLK | 11 | 23 |
| Display CS / CE0 | 8 | 24 |
| Display DC | 16 | 36 |
| Display RST | 26 | 37 |
| PLAY / PAUSE | 17 | 11 |
| PREVIOUS | 27 | 13 |
| NEXT | 22 | 15 |
| VOL_UP | 23 | 16 |
| VOL_DOWN | 24 | 18 |
| MENU | 25 | 22 |

Electrical constraints:
- Raspberry Pi GPIO is 3.3 V logic and is not 5 V tolerant.
- All modules must share a suitable common ground.
- Keep GPIO17/22/23/24/25/27 (buttons), GPIO7–11 (SPI0) and GPIO16/26 (display) reserved. The hardware agent rejects duplicate pins in `player.json`.
- Check for conflicts with SPI configuration, kernel overlays, and other software using the same GPIOs.

## 7. Component selection criteria

No final manufacturer part numbers are selected yet. Choose exact parts only after confirming availability, datasheets, dimensions, and module pinouts.

### M1 — charger / power-path
Must:
- Support one Li-ion/LiPo cell of the exact selected chemistry.
- Explicitly support load sharing/power-path while charging and running the load.
- Have suitable battery protection, or be used with a compatible protected battery/protection circuit.
- Specify maximum charge current and thermal limits.
- Have documented input, battery, and system pins.
- Avoid unexpected resets or unsafe current paths when USB is plugged/unplugged.

### M2 — boost converter
Must:
- Accept the full voltage range provided by M1's SYS output.
- Deliver regulated 5 V (nominal design target 5.1 V if verified acceptable).
- Be sized for Raspberry Pi transient demand and connected peripherals.
- Have documented output-current performance at low input voltage.
- Include appropriate short-circuit/thermal protections or be used in a suitably protected system.
- Be thermally viable inside the intended enclosure.

### J1 — battery connector
Must:
- Be polarized.
- Be rated for the expected continuous and peak current.
- Match the battery's existing connector or use a safe, correctly wired cable.
- Have suitable wire gauge and strain relief.

### J3 — display connector
Must:
- Match actual pad pitch or module connector.
- Match the verified pin order.
- Be rated for the display supply and signals.
- Provide mechanical retention appropriate to the enclosure.

### J4 — button module connector
Must:
- Be polarized.
- Have at least seven positions.
- Have sufficient retention for repeated assembly.
- Be clearly marked on the PCB and button-module PCB.

## 8. PCB layout guidelines

- Start with a two-layer PCB unless requirements show otherwise.
- Use the official Pi Zero 2 W board outline and mounting-hole geometry.
- Confirm how the carrier PCB physically relates to the Pi: stacked underneath, above, or beside it.
- Keep the battery/power conversion zone away from sensitive SPI signal routing where practical.
- Use a continuous ground plane where possible.
- Route high-current battery and 5 V paths with suitable width and minimal length.
- Follow the selected converter module/datasheet requirements for capacitors, current loops, and thermal clearance.
- Keep SPI traces reasonably short.
- Avoid routing display SPI signals through the switching regulator's high-noise area.
- Include mounting holes and clearance for the 3D-printed enclosure.
- Mark all connectors with names, pin 1, and power polarity.
- Include test pads for GND, 3V3, and 5V_SYS.
- Include board name, revision, and optional date/version text on silkscreen.
- Ensure connectors are accessible and cables can exit without bending sharply.
- Confirm connector height and clearance in KiCad 3D Viewer.

## 9. KiCad project and fabrication workflow

Recommended project files:

```text
OpenPlayer-PCB/
├── OpenPlayer-PCB.kicad_pro
├── OpenPlayer-PCB.kicad_sch
├── OpenPlayer-PCB.kicad_pcb
├── symbols/                  # custom symbols if needed
├── footprints/               # custom footprints if needed
├── scripts/
│   ├── validate.ps1
│   └── export-gerbers.ps1
├── fabrication/              # generated output; not source of truth
├── docs/
│   ├── requirements.md
│   ├── bom.md
│   ├── connector-pinout.md
│   └── bring-up-checklist.md
└── README.md
```

Suggested workflow:
1. Confirm physical dimensions and module pinouts.
2. Choose exact M1 and M2 modules from datasheets.
3. Draw the schematic and assign footprints.
4. Run Electrical Rules Checker (ERC).
5. Create the board outline, mounting holes, connector placement, and power zones.
6. Route the PCB.
7. Run Design Rules Checker (DRC).
8. Review the 3D model and compare it to the intended enclosure.
9. Verify polarity, connector orientation, pin numbering, net names, and power path independently.
10. Export Gerbers and drill files.
11. Open the exported files in a Gerber viewer and the manufacturer's online viewer.
12. Order a small prototype batch first; test power and safety before installing the Pi.
13. Do not treat a clean ERC/DRC report as proof that the battery power circuit is safe.

## 10. Validation and bring-up checklist

### Before fabrication
- [ ] Exact Pi footprint and mounting holes verified.
- [ ] Exact display module pinout, voltage and connector pitch verified.
- [ ] Button connector pin order verified.
- [ ] Battery chemistry, voltage limits, current capability and protection verified.
- [ ] M1 power-path functionality documented by datasheet.
- [ ] M1 system output voltage range documented.
- [ ] M2 input range and output current verified at minimum battery voltage.
- [ ] Pi supply path is unambiguous; no accidental dual feed.
- [ ] ERC clean or every remaining warning understood.
- [ ] DRC clean or every remaining warning understood.
- [ ] 3D clearance and connector orientation reviewed.
- [ ] Gerbers and drill files independently inspected.

### First power-up
- [ ] Do not connect the Raspberry Pi initially.
- [ ] Inspect PCB for shorts, solder bridges, reversed connectors and incorrect polarity.
- [ ] Use a current-limited bench supply where possible.
- [ ] Verify battery connector polarity with a meter.
- [ ] Verify M1 charging behavior and power-path behavior with a suitable test load.
- [ ] Verify regulated output voltage at low and high battery conditions.
- [ ] Check for excessive heating and voltage droop under load.
- [ ] Confirm no reverse feed into USB or battery input.
- [ ] Only then connect the Pi and check for stable boot.
- [ ] Test screen, each button, USB DAC, Wi-Fi, Bluetooth and simultaneous charging.
- [ ] Test unplugging USB while operating and reconnecting USB while operating.
- [ ] Confirm the Pi shuts down safely before the battery protection trips.

## 11. Open questions / design gates

The following must be resolved before the schematic can be considered production-ready:

1. Exact battery model, chemistry, connector, maximum discharge current, and whether protection is built into the pack.
2. Exact M1 charging module and its documented power-path behavior.
3. Whether M1 SYS output is raw battery voltage or regulated voltage.
4. Exact M2 boost module, input range, output-current rating at low input voltage, and thermal performance.
5. Whether Pi power is delivered through its micro-USB power port or a reviewed header-based route.
6. GC9A01 mounting arrangement, and whether to add a panel VCC switch (module has no BL pin).
7. Exact connector family/pitch for J1, J3, and J4.
8. Physical PCB dimensions and stack-up relative to the Pi and 3D-printed enclosure.
9. Whether a physical hard power switch is required. Safe shutdown already exists in software (hold PLAY/PAUSE 3 s → `systemctl poweroff`, SPEC 20); a hard switch is still needed to cut power (display backlight) after shutdown.
10. Whether the system must continue playing without interruption when USB power is connected or disconnected.

## 12. Explicit non-goals for Rev A

- Replacing the Raspberry Pi with an ESP32.
- Designing a custom audio DAC; the current USB DAC remains external.
- Adding the OLED display; the GC9A01 TFT is the target for this revision.
- Designing a lithium charger IC circuit from scratch before validating a replaceable module.
- Fabricating a production batch before electrical, mechanical, and thermal validation.
- Assuming any unverified module pinout, connector pitch, or advertised current rating is correct.

## 13. Definition of done

The Rev A design is ready to order as a prototype only when:

- The schematic reflects the selected real modules and their datasheets.
- Power-path and boost converter behavior are understood and documented.
- ERC and DRC have been reviewed.
- Connector pinouts and polarity are clearly marked.
- The 3D view and mechanical dimensions have been reviewed.
- Gerber and drill outputs have been inspected independently.
- A staged power-up and test plan is available.
- The BOM identifies each part, footprint, supplier/manufacturer part number where applicable, and any substitutions.

**Safety note:** This is a requirements brief, not a verified circuit design. Battery charging, protection, boost conversion, and power-path behavior must be validated against the actual component datasheets and tested before connecting the Raspberry Pi or enclosing the battery.
