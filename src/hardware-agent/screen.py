"""Dibujo de la pantalla redonda (SPEC 17): View → imagen RGB 240x240, sin hardware."""

import math
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

WIDTH = HEIGHT = 240
CENTER = WIDTH // 2
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"  # fonts-dejavu-core

BACKGROUND = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (140, 140, 140)
TRACK = (50, 50, 50)
ACCENT = (30, 185, 84)

RING_RADIUS = 114
RING_WIDTH = 6
TEXT_RADIUS = 96  # dentro del anillo (111–117 px), con margen

MESSAGES = {"offline": "Sin conexión", "mpd_error": "MPD no responde"}


@dataclass(frozen=True)
class View:
    status: str  # "playing" | "paused" | "stopped" | "offline" | "mpd_error"
    title: str | None = None
    artist: str | None = None
    position: int | None = None  # segundos
    duration: int | None = None
    volume: int | None = None


def render(view: View) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    message = MESSAGES.get(view.status)
    if message is None and view.status == "stopped" and not view.title:
        message = "Detenido"
    if message is not None:
        _text(draw, message, CENTER - 11, 22, WHITE, radius=WIDTH // 2 - 6)  # sin anillo: todo el ancho
        return image

    if view.duration and view.position is not None:
        _ring(draw, min(max(view.position / view.duration, 0), 1))
    _icon(draw, view.status, 60)
    _text(draw, view.title or "", 105, 22, WHITE)
    _text(draw, view.artist or "", 135, 16, GRAY)
    if view.volume is not None:
        _text(draw, f"Vol {view.volume}", 180, 16, GRAY)
    return image


@lru_cache(maxsize=None)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def _text(draw, text, top, size, color, radius=TEXT_RADIUS):
    font = _font(size)
    # Ancho útil: la cuerda del círculo en el borde de la línea más lejano al centro.
    edge = max(abs(top - CENTER), abs(top + size - CENTER))
    max_width = 2 * math.sqrt(max(radius ** 2 - edge ** 2, 0))
    draw.text((CENTER, top), fit(text, font, max_width), font=font, fill=color, anchor="mt")


def fit(text: str, font, max_width: float) -> str:
    """Corta con "…" hasta que entra en max_width."""
    if font.getlength(text) <= max_width:
        return text
    while text and font.getlength(text + "…") > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _ring(draw, fraction):
    r = RING_RADIUS + RING_WIDTH // 2
    box = (CENTER - r, CENTER - r, CENTER + r, CENTER + r)
    draw.arc(box, 0, 360, fill=TRACK, width=RING_WIDTH)
    if fraction > 0:
        # Pillow mide en grados desde las 3, en sentido horario: -90 son las 12.
        draw.arc(box, -90, -90 + 360 * fraction, fill=ACCENT, width=RING_WIDTH)


def _icon(draw, status, center_y):
    s = 12  # medio lado
    x, y = CENTER, center_y
    if status == "playing":
        draw.polygon([(x - s + 3, y - s), (x - s + 3, y + s), (x + s, y)], fill=WHITE)
    elif status == "paused":
        draw.rectangle((x - s, y - s, x - 4, y + s), fill=WHITE)
        draw.rectangle((x + 4, y - s, x + s, y + s), fill=WHITE)
    else:
        draw.rectangle((x - s + 2, y - s + 2, x + s - 2, y + s - 2), fill=WHITE)
