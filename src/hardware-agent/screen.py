"""Dibujo de la pantalla redonda (SPEC 17, modos SPEC 18): View → imagen RGB 240x240, sin hardware."""

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
VOLUME = (40, 120, 220)

RING_RADIUS = 114
RING_WIDTH = 6
TEXT_RADIUS = 96  # dentro del anillo (111–117 px), con margen
VOLUME_RADIUS = 104  # anillo interior del indicador de volumen (SPEC 18)
VOLUME_WIDTH = 4
TITLE_TOP, TITLE_SIZE = 88, 22

MESSAGES = {"offline": "Sin conexión", "mpd_error": "MPD no responde"}


@dataclass(frozen=True)
class View:
    status: str  # "playing" | "paused" | "stopped" | "offline" | "mpd_error"
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    position: int | None = None  # segundos
    duration: int | None = None
    volume: int | None = None
    queue_position: int | None = None  # 0-based; se muestra +1
    queue_length: int | None = None
    mode: str = "track"  # "track" | "clock", ya con el reloj automático aplicado
    clock: str | None = None  # "HH:MM", solo en modo reloj
    date: str | None = None  # "vie 24 oct", solo en modo reloj
    volume_popup: bool = False  # anillo interior y número grande
    scroll: int = 0  # desplazamiento del título en px


def render(view: View) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    message = MESSAGES.get(view.status)
    if message is None and view.status == "stopped" and not view.title and view.mode != "clock":
        message = "Detenido"
    if message is not None:
        _text(draw, message, CENTER - 11, 22, WHITE, radius=WIDTH // 2 - 6)  # sin anillo: todo el ancho
        return image

    if view.mode == "clock":
        _clock(draw, view)
    else:
        _track(image, draw, view)
    if view.volume_popup and view.volume is not None:
        _volume(draw, view.volume)  # al final: tapa el centro de cualquier modo
    return image


def _track(image, draw, view):
    if view.duration and view.position is not None:
        _ring(draw, _fraction(view))
    _icon(draw, view.status, 60)
    if view.status == "playing" and title_overflow(view.title) > 0:
        _scrolled_title(image, view.title, view.scroll)
    else:
        _text(draw, view.title or "", TITLE_TOP, TITLE_SIZE, WHITE)
    _text(draw, view.artist or "", 116, 16, GRAY)
    _text(draw, view.album or "", 138, 14, GRAY)
    if view.duration and view.position is not None:
        _text(draw, f"{_mmss(view.position)} / -{_mmss(view.duration - view.position)}", 162, 16, WHITE)
    if view.queue_position is not None and view.queue_length:
        _text(draw, f"{view.queue_position + 1} / {view.queue_length}", 186, 12, GRAY)


def _clock(draw, view):
    if view.status in ("playing", "paused") and view.duration and view.position is not None:
        _ring(draw, _fraction(view))
    draw.text((CENTER, 108), view.clock or "", font=_font(48), fill=WHITE, anchor="mm")
    _text(draw, view.date or "", 142, 16, GRAY)


def _volume(draw, volume):
    r = VOLUME_RADIUS + VOLUME_WIDTH // 2
    draw.ellipse((CENTER - r, CENTER - r, CENTER + r, CENTER + r), fill=BACKGROUND)
    _arc(draw, r, VOLUME_WIDTH, min(max(volume / 100, 0), 1), VOLUME)
    draw.text((CENTER, CENTER), str(volume), font=_font(64), fill=WHITE, anchor="mm")


def _fraction(view):
    return min(max(view.position / view.duration, 0), 1)


def _title_width() -> float:
    return _chord(TITLE_TOP, TITLE_SIZE, TEXT_RADIUS)


def title_overflow(title: str | None) -> int:
    """Píxeles que el título no entra en su línea (0 si cabe): el máximo de View.scroll."""
    if not title:
        return 0
    return max(math.ceil(_font(TITLE_SIZE).getlength(title) - _title_width()), 0)


def _scrolled_title(image, title, scroll):
    # El título completo en una tira del ancho de la línea, corrida -scroll px y pegada centrada.
    width = int(_title_width())
    strip = Image.new("RGB", (width, TITLE_SIZE + 8), BACKGROUND)
    offset = min(max(scroll, 0), title_overflow(title))
    ImageDraw.Draw(strip).text((-offset, 0), title, font=_font(TITLE_SIZE), fill=WHITE, anchor="lt")
    image.paste(strip, (CENTER - width // 2, TITLE_TOP))


def _mmss(seconds: int) -> str:
    return f"{max(seconds, 0) // 60}:{max(seconds, 0) % 60:02d}"


@lru_cache(maxsize=None)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def _text(draw, text, top, size, color, radius=TEXT_RADIUS):
    font = _font(size)
    draw.text((CENTER, top), fit(text, font, _chord(top, size, radius)), font=font, fill=color, anchor="mt")


def _chord(top, size, radius):
    """Ancho útil: la cuerda del círculo en el borde de la línea más lejano al centro."""
    edge = max(abs(top - CENTER), abs(top + size - CENTER))
    return 2 * math.sqrt(max(radius ** 2 - edge ** 2, 0))


def fit(text: str, font, max_width: float) -> str:
    """Corta con "…" hasta que entra en max_width."""
    if font.getlength(text) <= max_width:
        return text
    while text and font.getlength(text + "…") > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _ring(draw, fraction):
    _arc(draw, RING_RADIUS + RING_WIDTH // 2, RING_WIDTH, fraction, ACCENT)


def _arc(draw, r, width, fraction, color):
    box = (CENTER - r, CENTER - r, CENTER + r, CENTER + r)
    draw.arc(box, 0, 360, fill=TRACK, width=width)
    if fraction > 0:
        # Pillow mide en grados desde las 3, en sentido horario: -90 son las 12.
        draw.arc(box, -90, -90 + 360 * fraction, fill=color, width=width)


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
