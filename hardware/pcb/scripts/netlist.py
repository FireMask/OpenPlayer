"""OpenPlayer carrier PCB (SPEC 22): parts and nets, single source of truth.

build_sch.py and build_pcb.py import this module. Run it directly to check it
against config/player.example.json:  python hardware/pcb/scripts/netlist.py
"""

import json
from pathlib import Path

# ref → (value, symbol lib_id, footprint lib_id)
PARTS = {
    "J1": ("Pi_40pin_IDC", "Connector_Generic:Conn_02x20_Odd_Even", "Connector_IDC:IDC-Header_2x20_P2.54mm_Vertical"),
    "J2": ("PWR_IN", "Connector_Generic:Conn_01x02", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"),
    "J3": ("KEY", "Connector_Generic:Conn_01x02", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"),
    "J4": ("BUTTONS", "Connector_Generic:Conn_01x08", "Connector_JST:JST_XH_B8B-XH-A_1x08_P2.50mm_Vertical"),
    "J5": ("DISPLAY", "Connector_Generic:Conn_01x07", "Connector_PinSocket_2.54mm:PinSocket_1x07_P2.54mm_Vertical"),
    "J6": ("SWITCH", "Connector_Generic:Conn_01x02", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"),
    "C1": ("1000uF 10V", "Device:C_Polarized", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm"),
    "C2": ("100nF", "Device:C", "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"),
    "TP1": ("GND", "Connector:TestPoint", "TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm"),
    "TP2": ("5V_SYS", "Connector:TestPoint", "TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm"),
    "TP3": ("3V3", "Connector:TestPoint", "TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm"),
    "H1": ("M2.5", "Mechanical:MountingHole", "MountingHole:MountingHole_2.7mm_M2.5"),
    "H2": ("M2.5", "Mechanical:MountingHole", "MountingHole:MountingHole_2.7mm_M2.5"),
    "H3": ("M2.5", "Mechanical:MountingHole", "MountingHole:MountingHole_2.7mm_M2.5"),
    "H4": ("M2.5", "Mechanical:MountingHole", "MountingHole:MountingHole_2.7mm_M2.5"),
}

PI_GND_PINS = [6, 9, 14, 20, 25, 30, 34, 39]

# net → [(ref, pin)]. J1 pin N = Pi physical pin N (straight-through ribbon).
NETS = {
    "5V_IN": [("J2", "1"), ("J6", "1")],
    "5V_SYS": [("J6", "2"), ("J1", "2"), ("J1", "4"), ("C1", "1"), ("C2", "1"), ("TP2", "1")],
    "GND": [("J1", str(p)) for p in PI_GND_PINS]
    + [("J2", "2"), ("J3", "2"), ("J4", "1"), ("J5", "2"), ("C1", "2"), ("C2", "2"), ("TP1", "1")],
    "3V3": [("J1", "1"), ("J1", "17"), ("J5", "1"), ("TP3", "1")],
    "SPI_SCLK": [("J1", "23"), ("J5", "3")],
    "SPI_MOSI": [("J1", "19"), ("J5", "4")],
    "LCD_DC": [("J1", "36"), ("J5", "5")],
    "LCD_CS": [("J1", "24"), ("J5", "6")],
    "LCD_RST": [("J1", "37"), ("J5", "7")],
    "BTN_PLAY": [("J1", "11"), ("J4", "2")],
    "BTN_PREV": [("J1", "13"), ("J4", "3")],
    "BTN_NEXT": [("J1", "15"), ("J4", "4")],
    "BTN_VOLUP": [("J1", "16"), ("J4", "5")],
    "BTN_VOLDN": [("J1", "18"), ("J4", "6")],
    "BTN_MENU": [("J1", "22"), ("J4", "7")],
    "PWR_KEY": [("J4", "8"), ("J3", "1")],
}

# Pi 40-pin header: BCM GPIO → physical pin.
BCM_TO_PIN = {
    2: 3, 3: 5, 4: 7, 14: 8, 15: 10, 17: 11, 18: 12, 27: 13, 22: 15, 23: 16, 24: 18,
    10: 19, 9: 21, 25: 22, 11: 23, 8: 24, 7: 26, 0: 27, 1: 28, 5: 29, 6: 31, 12: 32,
    13: 33, 19: 35, 16: 36, 26: 37, 20: 38, 21: 40,
}

# player.json key → net it must land on.
CONFIG_NETS = {
    ("buttons", "play_pause"): "BTN_PLAY",
    ("buttons", "previous"): "BTN_PREV",
    ("buttons", "next"): "BTN_NEXT",
    ("buttons", "volume_up"): "BTN_VOLUP",
    ("buttons", "volume_down"): "BTN_VOLDN",
    ("buttons", "menu"): "BTN_MENU",
    ("display", "dc"): "LCD_DC",
    ("display", "rst"): "LCD_RST",
}
FIXED_NETS = {"SPI_SCLK": 11, "SPI_MOSI": 10, "LCD_CS": 8}  # SPI0, CE0


def pin_net():
    """(ref, pin) → net. Raises if a pin is in two nets."""
    owner = {}
    for net, pins in NETS.items():
        for rp in pins:
            assert rp not in owner, f"{rp} in both {owner[rp]} and {net}"
            owner[rp] = net
    return owner


def check(config_path):
    owner = pin_net()
    for ref, _ in owner:
        assert ref in PARTS, f"unknown part {ref}"
    hw = json.loads(Path(config_path).read_text(encoding="utf-8"))["hardware"]
    expected = {net: BCM_TO_PIN[hw[group][key]] for (group, key), net in CONFIG_NETS.items()}
    expected.update({net: BCM_TO_PIN[bcm] for net, bcm in FIXED_NETS.items()})
    for net, phys in expected.items():
        j1 = [p for r, p in NETS[net] if r == "J1"]
        assert j1 == [str(phys)], f"{net}: J1 pins {j1}, expected [{phys}]"
    assert {p for r, p in NETS["5V_SYS"] if r == "J1"} == {"2", "4"}
    assert {p for r, p in NETS["3V3"] if r == "J1"} == {"1", "17"}
    assert {p for r, p in NETS["GND"] if r == "J1"} == {str(p) for p in PI_GND_PINS}
    assert not any(r == "J1" for r, _ in NETS["PWR_KEY"]), "PWR_KEY must not reach the Pi"


if __name__ == "__main__":
    check(Path(__file__).resolve().parents[3] / "config" / "player.example.json")
    print("OK")
