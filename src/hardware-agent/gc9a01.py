"""Driver mínimo de la pantalla redonda GC9A01 240x240 por SPI (SPEC 17)."""

import time

from PIL import Image, ImageMath

WIDTH = HEIGHT = 240

CASET, RASET, RAMWR = 0x2A, 0x2B, 0x2C
SLPOUT, INVON, DISPON = 0x11, 0x21, 0x29

# Secuencia de init de referencia (Waveshare LCD_1inch28): (comando, datos).
# ponytail: secuencia fija; si un módulo muestra colores invertidos o espejados, se ajusta 0x36 (MADCTL) o INVON acá.
INIT_SEQUENCE = (
    (0xEF, b""), (0xEB, b"\x14"), (0xFE, b""), (0xEF, b""), (0xEB, b"\x14"),
    (0x84, b"\x40"), (0x85, b"\xFF"), (0x86, b"\xFF"), (0x87, b"\xFF"), (0x88, b"\x0A"),
    (0x89, b"\x21"), (0x8A, b"\x00"), (0x8B, b"\x80"), (0x8C, b"\x01"), (0x8D, b"\x01"),
    (0x8E, b"\xFF"), (0x8F, b"\xFF"), (0xB6, b"\x00\x20"),
    (0x36, b"\x08"),  # MADCTL: orden BGR del panel
    (0x3A, b"\x05"),  # 16 bits por píxel (RGB565)
    (0x90, b"\x08\x08\x08\x08"), (0xBD, b"\x06"), (0xBC, b"\x00"), (0xFF, b"\x60\x01\x04"),
    (0xC3, b"\x13"), (0xC4, b"\x13"), (0xC9, b"\x22"), (0xBE, b"\x11"),
    (0xE1, b"\x10\x0E"), (0xDF, b"\x21\x0C\x02"),
    (0xF0, b"\x45\x09\x08\x08\x26\x2A"), (0xF1, b"\x43\x70\x72\x36\x37\x6F"),
    (0xF2, b"\x45\x09\x08\x08\x26\x2A"), (0xF3, b"\x43\x70\x72\x36\x37\x6F"),
    (0xED, b"\x1B\x0B"), (0xAE, b"\x77"), (0xCD, b"\x63"),
    (0x70, b"\x07\x07\x04\x0E\x0F\x09\x07\x08\x03"), (0xE8, b"\x34"),
    (0x62, b"\x18\x0D\x71\xED\x70\x70\x18\x0F\x71\xEF\x70\x70"),
    (0x63, b"\x18\x11\x71\xF1\x70\x70\x18\x13\x71\xF3\x70\x70"),
    (0x64, b"\x28\x29\xF1\x01\xF1\x00\x07"),
    (0x66, b"\x3C\x00\xCD\x67\x45\x45\x10\x00\x00\x00"),
    (0x67, b"\x00\x3C\x00\x00\x00\x01\x54\x10\x32\x98"),
    (0x74, b"\x10\x85\x80\x00\x00\x4E\x00"), (0x98, b"\x3E\x07"),
    (0x35, b""), (INVON, b""),
)

# Rotación en sentido horario → transposición de Pillow (ROTATE_* gira antihorario).
TRANSPOSE = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}


class GC9A01:
    def __init__(self, spi, dc, rst, *, spi_hz: int, rotation: int, sleep=time.sleep):
        """spi: objeto con writebytes2 (spidev.SpiDev o falso en pruebas); dc/rst: DigitalOutputDevice."""
        self._spi, self._dc, self._rst = spi, dc, rst
        self._rotation = rotation
        self._sleep = sleep
        spi.max_speed_hz = spi_hz
        spi.mode = 0

    def init(self) -> None:
        self._rst.on()
        self._sleep(0.01)
        self._rst.off()
        self._sleep(0.01)
        self._rst.on()
        self._sleep(0.12)
        for command, data in INIT_SEQUENCE:
            self._command(command, data)
        self._command(SLPOUT)
        self._sleep(0.12)
        self._command(DISPON)
        self._sleep(0.02)

    def show(self, image: Image.Image) -> None:
        if self._rotation:
            image = image.transpose(TRANSPOSE[self._rotation])
        self._command(CASET, b"\x00\x00\x00\xEF")  # 0–239
        self._command(RASET, b"\x00\x00\x00\xEF")
        self._command(RAMWR, rgb565(image))

    def close(self) -> None:
        self._spi.close()
        self._dc.close()
        self._rst.close()

    def _command(self, command: int, data: bytes = b"") -> None:
        self._dc.off()
        self._spi.writebytes2(bytes([command]))
        if data:
            self._dc.on()
            self._spi.writebytes2(data)


def rgb565(image: Image.Image) -> bytes:
    """RGB → RGB565 big-endian (2 bytes por píxel), sin bucles en Python: la Pi Zero lo hace en milisegundos."""
    r, g, b = image.convert("RGB").split()
    high = ImageMath.eval("convert((r & 248) | (g >> 5), 'L')", r=r, g=g)
    low = ImageMath.eval("convert(((g << 3) & 224) | (b >> 3), 'L')", g=g, b=b)
    return Image.merge("LA", (high, low)).tobytes()
