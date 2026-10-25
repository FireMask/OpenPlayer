from dataclasses import replace

import pytest

from screen import ACCENT, CENTER, HEIGHT, VOLUME, WIDTH, View, _font, _mmss, fit, render, title_overflow

PLAYING = View("playing", "Song", "Artist", position=60, duration=120, volume=35)


@pytest.mark.parametrize("view", [
    PLAYING,
    View("paused", "Song", "Artist", position=10, duration=120, volume=35),
    View("stopped"),
    View("offline"),
    View("mpd_error"),
])
def test_renders_every_state(view):
    image = render(view)

    assert image.mode == "RGB"
    assert image.size == (WIDTH, HEIGHT)
    assert image.getbbox() is not None  # dibujó algo sobre el fondo negro


def test_message_states_differ():
    images = [render(View(s)).tobytes() for s in ("stopped", "offline", "mpd_error")]

    assert len(set(images)) == 3


def test_long_title_is_cut_with_ellipsis():
    font = _font(22)
    text = fit("A very long song title that never ends at all", font, 150)

    assert text.endswith("…")
    assert font.getlength(text) <= 150


def test_short_title_is_kept():
    assert fit("Song", _font(22), 150) == "Song"


def accent_pixels(image, side):
    xs = range(CENTER + 1, WIDTH) if side == "right" else range(0, CENTER - 1)
    return sum(1 for x in xs for y in range(HEIGHT) if image.getpixel((x, y)) == ACCENT)


def test_ring_at_half_covers_right_side_only():
    image = render(PLAYING)

    assert accent_pixels(image, "right") > 0
    assert accent_pixels(image, "left") == 0


def test_ring_grows_with_position():
    quarter = render(View("playing", "Song", position=30, duration=120))
    three_quarters = render(View("playing", "Song", position=90, duration=120))

    assert accent_pixels(three_quarters, "left") > accent_pixels(quarter, "left") == 0


def test_no_ring_without_duration():
    with_ring = render(PLAYING)
    without = render(View("playing", "Song", "Artist", position=60, duration=None, volume=35))

    assert accent_pixels(without, "right") == 0
    # Sin anillo ni pista: el borde queda negro.
    assert without.getpixel((CENTER, 3)) == (0, 0, 0) != with_ring.getpixel((CENTER, 3))


# Modo pista (SPEC 18)

FULL = View("playing", "Song", "Artist", album="Album", position=83, duration=243, volume=35,
            queue_position=2, queue_length=12)


def band(image, top, height):
    """¿Hay algo dibujado entre top y top+height? x 60–180 deja afuera el anillo."""
    return image.crop((60, top, WIDTH - 60, top + height)).getbbox() is not None


@pytest.mark.parametrize("field, top, height", [
    ("album", 138, 16),
    ("duration", 162, 18),
    ("queue_length", 186, 14),
])
def test_line_is_drawn_only_with_its_data(field, top, height):
    assert band(render(FULL), top, height)
    assert not band(render(replace(FULL, **{field: None})), top, height)


def test_volume_is_not_drawn():
    assert render(FULL).tobytes() == render(View(**{**FULL.__dict__, "volume": 90})).tobytes()


def test_time_line_changes_with_position():
    assert render(FULL).crop((20, 162, 220, 180)).tobytes() != render(replace(FULL, position=84)).crop((20, 162, 220, 180)).tobytes()


@pytest.mark.parametrize("seconds, text", [(0, "0:00"), (83, "1:23"), (600, "10:00"), (-3, "0:00")])
def test_mmss(seconds, text):
    assert _mmss(seconds) == text


def test_queue_without_position_is_not_drawn():
    assert not band(render(replace(FULL, queue_position=None)), 186, 14)


# Modo reloj, indicador de volumen y desplazamiento (SPEC 18)

def test_clock_mode_differs_from_track_and_changes_with_time():
    clock = replace(FULL, mode="clock", clock="21:47", date="vie 24 oct")

    assert render(clock).tobytes() != render(FULL).tobytes()
    assert render(clock).tobytes() != render(replace(clock, clock="21:48")).tobytes()
    assert render(clock).tobytes() != render(replace(clock, date="sáb 25 oct")).tobytes()


@pytest.mark.parametrize("status, ring", [("playing", True), ("paused", True), ("stopped", False)])
def test_clock_ring_only_with_track_playing_or_paused(status, ring):
    image = render(replace(FULL, status=status, mode="clock", clock="21:47", date="vie 24 oct"))

    assert (accent_pixels(image, "right") > 0) == ring


def test_stopped_clock_shows_time_instead_of_stopped_message():
    assert render(View("stopped", mode="clock", clock="07:05", date="sáb 25 oct")).tobytes() != render(View("stopped")).tobytes()


def volume_pixels(image):
    return sum(1 for x in range(WIDTH) for y in range(HEIGHT) if image.getpixel((x, y)) == VOLUME)


def test_volume_popup_draws_inner_ring_over_track_and_clock():
    assert volume_pixels(render(FULL)) == 0
    for view in (FULL, replace(FULL, mode="clock", clock="21:47", date="vie 24 oct")):
        popup = render(replace(view, volume_popup=True))
        assert volume_pixels(popup) > 0
        assert accent_pixels(popup, "right") > 0  # el anillo de progreso sigue
    # El anillo y el número cambian con el volumen.
    assert volume_pixels(render(replace(FULL, volume_popup=True, volume=80))) > volume_pixels(render(replace(FULL, volume_popup=True)))


def test_title_overflow():
    assert title_overflow("Song") == 0
    assert title_overflow(None) == 0
    assert title_overflow("A very long song title that never ends at all") > 100


LONG = "A very long song title that never ends at all"


def title_band(view):
    return render(view).crop((0, 88, WIDTH, 112)).tobytes()


def test_long_title_scrolls_while_playing_and_clamps():
    view = replace(FULL, title=LONG)
    end = title_overflow(LONG)

    assert title_band(view) != title_band(replace(view, scroll=10))
    assert title_band(replace(view, scroll=end)) == title_band(replace(view, scroll=end + 50))
    # En pausa no se desplaza: corte con "…".
    paused = replace(view, status="paused")
    assert title_band(paused) == title_band(replace(paused, scroll=10))


def test_short_title_ignores_scroll():
    assert title_band(FULL) == title_band(replace(FULL, scroll=10))


# Modo carátula (SPEC 19)

def red_cover():
    from cover import SIZE
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (SIZE, SIZE))
    ImageDraw.Draw(image).ellipse((0, 0, SIZE - 1, SIZE - 1), fill=(200, 0, 0))
    return image


ART = replace(FULL, mode="art")


def test_art_mode_fills_circle_with_cover_and_keeps_ring():
    image = render(replace(ART, cover=red_cover()))

    assert image.getpixel((CENTER, CENTER)) == (200, 0, 0)
    assert image.getpixel((CENTER, 20)) == (200, 0, 0)  # cerca del borde, dentro del anillo
    assert accent_pixels(image, "right") > 0  # el anillo de progreso queda encima
    assert image.getpixel((0, 0)) == (0, 0, 0)


def test_art_mode_without_cover_shows_placeholder_with_title():
    placeholder = render(ART)

    assert placeholder.tobytes() != render(FULL).tobytes()
    assert band(placeholder, 140, 22)  # título
    assert band(placeholder, 64, 64)  # ♪
    assert placeholder.tobytes() != render(replace(ART, title="Other")).tobytes()


def test_art_mode_has_no_text_over_cover():
    with_cover = render(replace(ART, cover=red_cover()))

    # Cambiar título, artista o álbum no cambia nada: no hay texto.
    assert with_cover.tobytes() == render(replace(ART, cover=red_cover(), title="X", artist="Y", album="Z")).tobytes()


def test_volume_popup_over_art():
    popup = render(replace(ART, cover=red_cover(), volume_popup=True))

    assert volume_pixels(popup) > 0
    assert popup.getpixel((CENTER, CENTER)) != (200, 0, 0)  # el número tapa el centro
    # Nada de la carátula entre el anillo de volumen y el de progreso.
    red = [(x, y) for x in range(WIDTH) for y in range(HEIGHT) if popup.getpixel((x, y)) == (200, 0, 0)]
    assert red == []


def test_art_mode_stopped_without_track_shows_stopped_message():
    assert render(View("stopped", mode="art")).tobytes() == render(View("stopped")).tobytes()


# Avisos de gestos (SPEC 20)

TOAST_PILL = (CENTER, 169)  # borde superior de la píldora, sin texto


@pytest.mark.parametrize("view", [FULL, ART, replace(FULL, mode="clock", clock="21:47"), View("offline"),
                                  replace(FULL, volume_popup=True)])
def test_toast_pill_over_every_mode(view):
    image = render(replace(view, toast="+10 s"))

    assert image.getpixel(TOAST_PILL) == (40, 40, 40)
    assert image.tobytes() != render(view).tobytes()


def test_toast_over_cover():
    image = render(replace(ART, cover=red_cover(), toast="+10 s"))

    assert image.getpixel(TOAST_PILL) == (40, 40, 40)


def test_long_toast_fits_inside_circle():
    image = render(View("offline", toast="Menú: próximamente"))
    row = [x for x in range(WIDTH) if image.getpixel((x, 180)) != (0, 0, 0)]

    # La cuerda en el borde inferior de la píldora (y=193) mide ~190 px: todo dentro del círculo.
    assert CENTER - 95 <= row[0] and row[-1] <= CENTER + 95
    # Sin "…": la píldora mide el texto completo (172 px a 16 px) más el margen.
    assert row[-1] - row[0] >= _font(16).getlength("Menú: próximamente") + 14


def test_no_toast_draws_nothing_extra():
    assert render(replace(FULL, toast=None)).tobytes() == render(FULL).tobytes()
