import pytest

from screen import ACCENT, CENTER, HEIGHT, WIDTH, View, _font, fit, render

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
