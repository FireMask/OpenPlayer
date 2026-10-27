# OpenPlayer Rev B — Shopping List

Everything to buy before ordering the carrier (`hardware/pcb/`) and button board (`hardware/buttons/`) from JLCPCB. Sources: `hardware/pcb/fabrication/openplayer-carrier-bom.csv`, `hardware/buttons/fabrication/openplayer-buttons-bom.csv`, `docs/pcb-requirements.md`.

Search tip: JST-XH is 2.50 mm pitch, but most Mexican and Chinese sellers list it as "2.54 mm". Both fit. Buy spares: connectors and crimps are cheap, and a missing one stops the build.

## 1. Carrier board parts (soldered to the PCB)

| Ref | Qty (+spare) | What | Also known as / search terms |
|---|---|---|---|
| J1 | 1 (+1) | 2 × 20, 2.54 mm **shrouded, right-angle (90°)** box header, 40 pins | IDC box header 40P 90°; shrouded header 2x20 right angle; DC3-40 90°; "conector IDC macho 40 pines ángulo recto"; "header caja 2x20 90 grados" |
| J2, J3, J6 | 3 (+2) | JST-XH 2-pin, **side entry** (horizontal) | JST **S2B-XH-A**; XH 2P right angle; "conector JST XH 2 pines 90°/horizontal" |
| J4 | 1 (+1) | JST-XH 8-pin, side entry | JST **S8B-XH-A**; XH 8P right angle |
| J5 | 1 (+1) | JST-XH 7-pin, side entry | JST **S7B-XH-A**; XH 7P right angle |
| C1 | 1 (+1) | 470 µF electrolytic, ≥ 10 V, **Ø 8 mm, 3.5 mm pitch** (optional) | 470uF 10V/16V 8×11.5 mm; "capacitor electrolítico 470 µF 16 V radial 8 mm" |
| C2 | 1 (+4) | 100 nF ceramic, 5 mm pitch, ≥ 16 V | "104" ceramic disc; 0.1 µF; 100 nF MLCC radial 5.08 mm; "capacitor cerámico 104" |

Note: shop listings for "XH 2.54 right angle" usually are the S*B-XH-A type (side entry). Check the photo: the pins bend 90° and the mouth faces sideways, not up.

## 2. Button board parts

| Ref | Qty (+spare) | What | Also known as / search terms |
|---|---|---|---|
| J1 | 1 (+1) | JST-XH 8-pin, **top entry** (vertical) | JST **B8B-XH-A**; XH 8P straight/vertical; "conector JST XH 8 pines recto" |
| SW1–SW7 | 7 (+5) | 6 × 6 mm THT tactile switch, 4 legs | tact switch 6x6; push button 6x6x(4.3…13) mm; TS-1101 / TS663 style; "botón táctil 6x6 4 pines"; "micro pulsador 6x6" |

Switch height (4.3–13 mm) depends on the enclosure's button caps; all heights share the footprint. Buying a mixed-height assortment kit is the cheap way to decide later.

## 3. Cables and crimping

The board connectors need mating cables. Either buy pre-crimped leads or crimp them yourself.

| Cable | Qty | Parts | Also known as / search terms |
|---|---|---|---|
| Pi ribbon (J1 → Pi header) | 1 (+1) | 40-pin, 1.27 mm flat ribbon, IDC female both ends, straight-through, **≤ 10 cm** | GPIO ribbon cable Raspberry Pi; 40P IDC F-F flat cable; "cable plano 40 pines hembra hembra"; "cable bus IDE 40 pines" (old 40-wire IDE cables work if the wire count is 40, not 80) |
| Button cable (J4 ↔ button J1) | 1 | XH-8 ↔ XH-8, **straight** (pin 1 → pin 1) | "cable JST XH 8 pines doble punta"; XH 8P double-ended |
| Display cable (J5 → display) | 1 | XH-7 one end, 1 × 7 Dupont **female** other end, straight | XH 7P single-ended pigtail + Dupont 1×7 housing; "cable JST XH 7 pines un extremo" |
| Power pigtails (J2, J3, J6) | 3 | XH-2 one end, bare wire other end (soldered to module pads / switch) | "cable JST XH 2 pines con conector"; XH 2P pigtail |

If crimping yourself:

| Part | Qty | Also known as |
|---|---|---|
| XH housing 2-pin | 3 (+3) | JST **XHP-2**; XH 2P female housing |
| XH housing 7-pin | 1 (+1) | JST **XHP-7** |
| XH housing 8-pin | 2 (+1) | JST **XHP-8** |
| XH crimp terminal | 30 (+30) | JST **SXH-001T-P0.6** (26–28 AWG) or **SXH-002T-P0.6** (22–26 AWG); "terminal hembra JST XH" |
| Dupont housing 1 × 7 | 1 (+1) | 1×7 2.54 mm housing; "carcasa Dupont 7 pines" |
| Dupont female terminal | 7 (+10) | Dupont female crimp pin 2.54 mm; "terminal hembra Dupont" |
| Crimper | 1 | IWISS **SN-28B** / **SN-01BM** / PA-09 ("pinza crimpadora JST Dupont") |
| 40-pin IDC female sockets + ribbon (to build a ≤ 10 cm ribbon) | 2 + 10 cm | **FC-40P** IDC socket; 40-wire 1.27 mm flat cable; press closed with a vise |
| Easier alternative | 1 kit | "kit conectores JST XH 2.54 con terminales" / "XH 2.54 connector kit 560 pcs" (includes housings, terminals, side/vertical headers) |

Wire: 22 AWG silicone (red/black) for the 5 V and switch pigtails (2 A); 26 AWG for signal cables. Heat-shrink tubing.

## 4. Panel switch and hardware

| Item | Qty | Also known as / search terms |
|---|---|---|
| Panel power switch, ≥ 3 A, SPST | 1 (+1) | mini rocker **KCD1-101** (6 A/250 V, 2 pins); toggle **MTS-101/MTS-102**; slide switch ≥ 3 A; "switch balancín mini 2 pines"; "interruptor palanca miniatura" |
| M2.5 standoffs + screws (carrier, 4 holes) | 4 sets | M2.5 nylon/brass standoff kit; "separadores M2.5 Raspberry Pi" (same kit fits the Pi Zero) |
| M2 screws + nuts/standoffs (button board, 2 holes) | 2 sets | M2 × 6 screws; "tornillos M2" |

## 5. Already owned? Verify before ordering

Not on the PCB BOM, but the PCB is useless without them. Each must match `docs/pcb-requirements.md`.

| Item | Also known as / search terms |
|---|---|
| Raspberry Pi Zero 2 W **with soldered header** (or a 2 × 20 2.54 mm male header to solder) | Pi Zero 2 WH; RPi Zero 2W; "Raspberry Pi Zero 2 W con header"; "tira de pines macho 2x20" |
| GC9A01 1.28" round TFT, 240 × 240, SPI, 7 pins (VCC GND SCL SDA DC CS RST) | 1.28 inch round LCD; "1.28 TFT ver 1.0"; "pantalla redonda 1.28 GC9A01" |
| FM5324GA USB-C charge/boost module, 5 V / 2 A out, `K` pad | DWEII 5V 2A boost charger (Amazon MX B09YD5C9QC); "módulo cargador elevador 18650 USB-C 5V 2A"; "power bank module 5V 2A Type-C" |
| 1-cell Li-ion/LiPo, 3.7 V, ~5000 mAh, **with protection board** | 3.7V 5000mAh LiPo (e.g. 105070/906090); "batería lipo 3.7 v 5000 mah con protección" |
| USB DAC + micro-USB OTG adapter | USB sound card; "adaptador OTG micro USB" |

## 6. Where to buy (Mexico / Monterrey)

Prices and stock change; check the listing photo against the part names above.

**Online, ships to Monterrey**

| Store | Good for |
|---|---|
| [Mercado Libre](https://www.mercadolibre.com.mx) | Everything here: XH kits, pre-crimped cables, tact switches, KCD1, standoffs, LiPo. Search the Spanish terms above. Many sellers are in Monterrey or CDMX (1–3 days) |
| [Geek Factory](https://www.mercadolibre.com.mx/pagina/geekfactorymx) (Mercado Libre store) | Raspberry Pi, displays, modules |
| [UNIT Electronics](https://uelectronics.com) | Pi, displays, connectors, maker parts (CDMX, ships nationwide) |
| [AG Electrónica](https://www.agelectronica.com) | Connectors, capacitors, switches, IDC parts (CDMX, ships nationwide) |
| [Steren](https://www.steren.com.mx) | Switches, wire, heat-shrink, basic capacitors; has physical stores in Monterrey |
| [Amazon México](https://www.amazon.com.mx) | FM5324GA module, connector/crimp kits, crimper, standoff kits |
| [DigiKey México](https://www.digikey.com.mx) / [Mouser México](https://www.mx.mouser.com) / [TME México](https://www.tme.com/mx/en/) | Genuine JST parts by exact part number (S2B-XH-A, XHP-8, SXH-001T-P0.6…); free shipping above a minimum order |
| [LCSC](https://www.lcsc.com) | Cheapest genuine/compatible parts; can ship in the same box as the JLCPCB order |
| AliExpress | Cheapest kits and cables; 2–4 weeks |

**Local, Monterrey (call or check Google Maps first; not verified)**

| Store | Notes |
|---|---|
| Steren (several branches, e.g. Centro, malls) | Switches, wire, heat-shrink, some capacitors and pin headers; JST-XH and IDC parts unlikely |
| Semty Electrónica (Centro de Monterrey) | Student electronics store; ask for "conectores JST XH", "header IDC 40 pines", "botones 6x6" |
| Electronics shops on Calle Colón / Juárez, Centro | Several small component shops in the downtown area; good for capacitors, tact switches, ribbon cable |

**JLCPCB assembly alternative:** JLCPCB can solder the THT connectors and capacitors for you (THT assembly, parts from LCSC). That removes §1 and §2 from this list, but not the cables in §3.
