import pytest
from gpiozero import Device, DigitalOutputDevice
from gpiozero.pins.mock import MockFactory
from PIL import Image

from gc9a01 import CASET, DISPON, HEIGHT, INIT_SEQUENCE, RAMWR, RASET, SLPOUT, WIDTH, GC9A01, rgb565

DC, RST = 5, 6


class FakeSpi:
    """Guarda cada escritura junto con el valor de DC en ese momento."""

    def __init__(self, dc):
        self.dc = dc
        self.writes = []  # (dc, bytes)
        self.closed = False

    def writebytes2(self, data):
        self.writes.append((self.dc.value, bytes(data)))

    def close(self):
        self.closed = True

    def commands(self):
        """[(comando, datos)] reconstruidos a partir de DC."""
        result = []
        for dc, data in self.writes:
            if dc == 0:
                result.append((data[0], b""))
            else:
                result[-1] = (result[-1][0], result[-1][1] + data)
        return result


@pytest.fixture
def factory():
    Device.pin_factory = MockFactory()
    yield Device.pin_factory
    Device.pin_factory.reset()
    Device.pin_factory = None


@pytest.fixture
def panel(factory):
    def make(rotation=0):
        dc, rst = DigitalOutputDevice(DC), DigitalOutputDevice(RST)
        spi = FakeSpi(dc)
        return GC9A01(spi, dc, rst, spi_hz=40_000_000, rotation=rotation, sleep=lambda _: None), spi
    return make


def test_configures_spi(panel):
    _, spi = panel()

    assert spi.max_speed_hz == 40_000_000
    assert spi.mode == 0


def test_init_pulses_reset_then_sends_sequence_ending_in_dispon(factory, panel):
    display, spi = panel()
    display.init()

    factory.pin(RST).assert_states([False, True, False, True])
    commands = spi.commands()
    assert commands[:len(INIT_SEQUENCE)] == list(INIT_SEQUENCE)
    assert commands[-2:] == [(SLPOUT, b""), (DISPON, b"")]
    assert (0x3A, b"\x05") in commands  # RGB565


def test_show_sends_window_and_full_frame(panel):
    display, spi = panel()
    display.show(Image.new("RGB", (WIDTH, HEIGHT)))

    assert spi.commands() == [
        (CASET, b"\x00\x00\x00\xEF"),
        (RASET, b"\x00\x00\x00\xEF"),
        (RAMWR, bytes(WIDTH * HEIGHT * 2)),
    ]
    assert [dc for dc, _ in spi.writes] == [0, 1, 0, 1, 0, 1]


@pytest.mark.parametrize("color, word", [
    ((255, 0, 0), 0xF800),
    ((0, 255, 0), 0x07E0),
    ((0, 0, 255), 0x001F),
    ((255, 255, 255), 0xFFFF),
    ((8, 4, 8), 0x0821),
])
def test_rgb565_big_endian(color, word):
    assert rgb565(Image.new("RGB", (1, 1), color)) == word.to_bytes(2, "big")


def test_rgb565_matches_reference_on_gradient():
    image = Image.new("RGB", (64, 4))
    image.putdata([(i * 4, 255 - i * 4, (i * 37) % 256) for i in range(64)] * 4)

    expected = b"".join((((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)).to_bytes(2, "big")
                        for r, g, b in image.getdata())
    assert rgb565(image) == expected


def test_rotation_180_flips_image(panel):
    image = Image.new("RGB", (WIDTH, HEIGHT))
    image.putpixel((0, 0), (255, 0, 0))  # arriba a la izquierda

    display, spi = panel(rotation=180)
    display.show(image)

    frame = spi.commands()[-1][1]
    assert frame[:2] == b"\x00\x00"
    assert frame[-2:] == b"\xF8\x00"  # abajo a la derecha


def test_close_releases_spi_and_pins(panel):
    display, spi = panel()
    display.close()

    assert spi.closed
