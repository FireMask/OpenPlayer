"""OpenPlayer button board (SPEC 23, 6 keys: SPEC 25): parts and nets, single source of truth.

build_sch.py and build_pcb.py import this module. Run it directly to check J1 against the
carrier's J4 (same pinout, straight cable):  python hardware/buttons/scripts/netlist.py
"""

import importlib.util
from pathlib import Path

SWITCH = ("Switch:SW_Push", "Button_Switch_THT:SW_PUSH_6mm")  # 6×6 THT tactile, height per enclosure
HOLE = ("Mechanical:MountingHole", "MountingHole:MountingHole_2.2mm_M2")

# ref → (value, symbol lib_id, footprint lib_id). SW2–SW7 top to bottom (SW1 POWER moved to the carrier's J7).
PARTS = {
    "SW2": ("VOL+", *SWITCH),
    "SW3": ("VOL-", *SWITCH),
    "SW4": ("PREV", *SWITCH),
    "SW5": ("PLAY", *SWITCH),
    "SW6": ("NEXT", *SWITCH),
    "SW7": ("MENU", *SWITCH),
    "J1": ("CARRIER", "Connector_Generic:Conn_01x08", "Connector_JST:JST_XH_B8B-XH-A_1x08_P2.50mm_Vertical"),
    "H1": ("M2", *HOLE),
    "H2": ("M2", *HOLE),
}

DESCRIPTIONS = {ref: "6x6 THT tactile, height per enclosure" for ref in PARTS if ref.startswith("SW")}  # BOM

# net → [(ref, pin)]. Net names and J1 pins are the carrier's J4: J1 pin N = J4 pin N; pin 8 (PWR_KEY) is a no-connect.
NETS = {
    "GND": [("J1", "1")] + [(f"SW{i}", "2") for i in range(2, 8)],
    "BTN_VOLUP": [("J1", "5"), ("SW2", "1")],
    "BTN_VOLDN": [("J1", "6"), ("SW3", "1")],
    "BTN_PREV": [("J1", "3"), ("SW4", "1")],
    "BTN_PLAY": [("J1", "2"), ("SW5", "1")],
    "BTN_NEXT": [("J1", "4"), ("SW6", "1")],
    "BTN_MENU": [("J1", "7"), ("SW7", "1")],
}


def pin_net():
    """(ref, pin) → net. Raises if a pin is in two nets."""
    owner = {}
    for net, pins in NETS.items():
        for rp in pins:
            assert rp not in owner, f"{rp} in both {owner[rp]} and {net}"
            owner[rp] = net
    return owner


def carrier_nets():
    """The carrier's NETS (both modules are called netlist, so load it by path)."""
    path = Path(__file__).resolve().parents[2] / "pcb" / "scripts" / "netlist.py"
    spec = importlib.util.spec_from_file_location("carrier_netlist", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.NETS


def check():
    owner = pin_net()
    for ref, _ in owner:
        assert ref in PARTS, f"unknown part {ref}"
    j4 = {p: net for net, pins in carrier_nets().items() for r, p in pins if r == "J4"}
    j1 = {p: net for (r, p), net in owner.items() if r == "J1"}
    assert sorted(j4, key=int) == [str(n) for n in range(1, 9)], f"carrier J4 pins {sorted(j4)}"
    assert "8" not in j1, "J1 pin 8 (PWR_KEY) must be unconnected"
    for n in range(1, 8):
        assert j1.get(str(n)) == j4[str(n)], f"J1 pin {n} is {j1.get(str(n))}, carrier J4 pin {n} is {j4[str(n)]}"
    for ref in PARTS:
        if ref.startswith("SW"):
            sig, gnd = owner.get((ref, "1")), owner.get((ref, "2"))
            assert gnd == "GND" and sig not in (None, "GND"), f"{ref}: pin 1 must be a signal and pin 2 GND, got {sig}, {gnd}"


if __name__ == "__main__":
    check()
    print("OK")
