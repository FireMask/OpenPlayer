import json
import logging
import socket
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from display import SCROLL_PAUSE, SCROLL_SPEED, Display, parse, scroll_offset
from screen import View, render, title_overflow


def wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met within timeout")


def snapshot(state="playing", title="Song", artist="Artist", position=10, duration=100, volume=35, mode="track"):
    return {"type": "player.snapshot", "state": state, "trackTitle": title, "trackArtist": artist,
            "positionSeconds": position, "durationSeconds": duration, "volume": volume,
            "queuePosition": 0, "queueVersion": 1, "displayMode": mode}


class FakeClock:
    """monotonic() y now() controlados por la prueba: el tiempo solo avanza con advance()."""

    START = datetime(2026, 10, 24, 21, 47, 30)  # sábado

    def __init__(self):
        self.t = 1000.0

    def advance(self, seconds):
        self.t += seconds

    def monotonic(self):
        return self.t

    def now(self):
        return self.START + timedelta(seconds=self.t - 1000.0)


class FakeService:
    """Service falso por TCP: acepta suscripciones y empuja líneas a la conexión activa."""

    def __init__(self):
        self.available = True
        self.subscriptions = []  # primera línea de cada conexión
        self._conns = []
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._port = self._listener.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def connect(self):
        if not self.available:
            raise ConnectionRefusedError("fake service unavailable")
        return socket.create_connection(("127.0.0.1", self._port), timeout=1)

    def push(self, message):
        self._conns[-1].sendall((json.dumps(message) + "\n").encode("utf-8"))

    def drop(self):
        for conn in self._conns:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()

    def close(self):
        self.drop()
        self._listener.close()

    def _accept(self):
        while True:
            try:
                conn, _ = self._listener.accept()
            except OSError:
                return
            line = conn.makefile("rb").readline()
            self.subscriptions.append(json.loads(line))
            self._conns.append(conn)


class FakePanel:
    def __init__(self, fail=False):
        self.fail = fail
        self.images = []

    def init(self):
        if self.fail:
            raise OSError("no SPI")

    def show(self, image):
        self.images.append(image.tobytes())

    def shows(self, view):
        return render(view).tobytes() in self.images


@pytest.fixture
def service():
    s = FakeService()
    yield s
    s.close()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def display(service, clock):
    created = []

    def make(panel=None, tick_seconds=0.05, retry_seconds=0.1, idle_clock_seconds=60, real_clock=False):
        panel = panel or FakePanel()
        times = {} if real_clock else {"now": clock.now, "monotonic": clock.monotonic}
        d = Display("/x.sock", panel, connect=service.connect, tick_seconds=tick_seconds, retry_seconds=retry_seconds,
                    idle_clock_seconds=idle_clock_seconds, **times)
        d.start()
        created.append(d)
        return d, panel

    yield make
    for d in created:
        d.stop()


PLAYING = View("playing", "Song", "Artist", position=10, duration=100, volume=35, queue_position=0)


def test_subscribes_and_shows_initial_snapshot(service, display):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot())

    assert service.subscriptions[0] == {"type": "player.subscribe"}
    wait_until(lambda: panel.shows(PLAYING))


def test_new_push_redraws(service, display):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state="paused"))
    service.push(snapshot(state="paused", title="Other"))

    wait_until(lambda: panel.shows(View("paused", "Other", "Artist", position=10, duration=100, volume=35, queue_position=0)))


def test_same_view_does_not_redraw(service, display):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state="paused"))
    wait_until(lambda: panel.shows(View("paused", "Song", "Artist", position=10, duration=100, volume=35, queue_position=0)))
    count = len(panel.images)

    service.push(snapshot(state="paused"))
    time.sleep(0.3)  # varios ticks
    assert len(panel.images) == count


def test_service_down_shows_offline_and_resubscribes(service, display):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot())
    wait_until(lambda: panel.shows(PLAYING))

    service.available = False
    service.drop()
    count = len(panel.images)
    wait_until(lambda: len(panel.images) > count and panel.images[-1] == render(View("offline")).tobytes())

    service.available = True
    wait_until(lambda: len(service.subscriptions) == 2, timeout=2.5)
    service.push(snapshot(title="Back"))
    wait_until(lambda: panel.shows(View("playing", "Back", "Artist", position=10, duration=100, volume=35, queue_position=0)))


def test_starts_offline_without_service(service, display):
    service.available = False
    _, panel = display()

    wait_until(lambda: panel.shows(View("offline")))


def test_error_line_shows_mpd_error(service, display):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push({"type": "error", "request": "player.get_snapshot", "message": "MPD unavailable"})

    wait_until(lambda: panel.shows(View("mpd_error")))


def test_position_advances_while_playing(service, display, clock):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(position=10))
    wait_until(lambda: panel.shows(PLAYING))

    clock.advance(2)
    wait_until(lambda: panel.shows(replace(PLAYING, position=12)))


def test_position_stops_at_duration(service, display, clock):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(position=98, duration=100))
    wait_until(lambda: panel.shows(View("playing", "Song", "Artist", position=98, duration=100, volume=35, queue_position=0)))
    clock.advance(10)
    wait_until(lambda: panel.shows(View("playing", "Song", "Artist", position=100, duration=100, volume=35, queue_position=0)))
    count = len(panel.images)
    time.sleep(0.2)  # varios ticks: la vista queda en 100 y no se redibuja

    assert len(panel.images) == count


@pytest.mark.parametrize("state", ["paused", "stopped"])
def test_position_does_not_advance_when_not_playing(service, display, clock, state):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state=state, position=10))
    wait_until(lambda: panel.shows(View(state, "Song", "Artist", position=10, duration=100, volume=35, queue_position=0)))
    clock.advance(5)
    time.sleep(0.2)

    assert not panel.shows(View(state, "Song", "Artist", position=11, duration=100, volume=35, queue_position=0))


def test_init_failure_logs_error_and_ends_thread(display, caplog):
    with caplog.at_level(logging.ERROR):
        d, panel = display(FakePanel(fail=True))
        wait_until(lambda: not d._thread.is_alive())

    assert "display init failed: no SPI" in caplog.text
    assert panel.images == []


def test_stop_ends_thread(service, display):
    d, _ = display()
    wait_until(lambda: service.subscriptions)
    d.stop()

    assert not d._thread.is_alive()


@pytest.mark.parametrize("line, view", [
    (b'{"type":"player.snapshot","state":"stopped","trackTitle":null}', View("stopped")),
    (b'{"type":"player.snapshot","state":"weird"}', View("stopped")),
    (b'{"type":"error","message":"x"}', View("mpd_error")),
    (b'{"type":"ok"}', None),
    (b'[1]', None),
    (b'not json', None),
])
def test_parse(line, view):
    assert parse(line) == view


# Modos, reloj automático e indicador de volumen (SPEC 18)

CLOCK = {"mode": "clock", "clock": "21:47", "date": "sáb 24 oct"}


def last_view_is(panel, view):
    return panel.images and panel.images[-1] == render(view).tobytes()


def test_parse_reads_new_fields():
    line = json.dumps({**snapshot(), "trackAlbum": "Album", "queuePosition": 2, "queueLength": 12,
                       "displayMode": "clock"}).encode()

    assert parse(line) == View("playing", "Song", "Artist", album="Album", position=10, duration=100, volume=35,
                               queue_position=2, queue_length=12, mode="clock")


@pytest.mark.parametrize("mode", [None, "weird", 3])
def test_parse_unknown_mode_is_track(mode):
    assert parse(json.dumps({**snapshot(), "displayMode": mode}).encode()).mode == "track"


def test_service_clock_mode_shows_local_time_and_spanish_date(service, display):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(mode="clock"))

    wait_until(lambda: last_view_is(panel, replace(PLAYING, **CLOCK)))


def test_clock_redraws_when_minute_changes_not_every_tick(service, display, clock):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state="paused", mode="clock"))
    paused = View("paused", "Song", "Artist", position=10, duration=100, volume=35, queue_position=0, **CLOCK)
    wait_until(lambda: last_view_is(panel, paused))
    count = len(panel.images)

    clock.advance(20)  # 21:47:50
    time.sleep(0.2)
    assert len(panel.images) == count

    clock.advance(15)  # 21:48:05
    wait_until(lambda: last_view_is(panel, replace(paused, clock="21:48")))
    assert len(panel.images) == count + 1


@pytest.mark.parametrize("days, date", [(1, "dom 25 oct"), (2, "lun 26 oct"), (8, "dom 1 nov")])
def test_date_uses_spanish_names(service, display, clock, days, date):
    clock.advance(days * 86400)
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state="paused", mode="clock"))

    wait_until(lambda: last_view_is(panel, View("paused", "Song", "Artist", position=10, duration=100, volume=35,
                                                queue_position=0, mode="clock", clock="21:47", date=date)))


@pytest.mark.parametrize("state", ["paused", "stopped"])
def test_idle_shows_clock_after_idle_seconds_and_playing_returns_to_track(service, display, clock, state):
    _, panel = display(idle_clock_seconds=60)
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state=state))
    idle = View(state, "Song", "Artist", position=10, duration=100, volume=35, queue_position=0)
    wait_until(lambda: last_view_is(panel, idle))

    clock.advance(59)
    time.sleep(0.2)
    assert last_view_is(panel, idle)

    clock.advance(1)  # 21:48:30
    wait_until(lambda: last_view_is(panel, replace(idle, mode="clock", clock="21:48", date="sáb 24 oct")))

    service.push(snapshot())
    wait_until(lambda: last_view_is(panel, PLAYING))


def test_repeated_paused_snapshots_do_not_restart_idle_timer(service, display, clock):
    _, panel = display(idle_clock_seconds=60)
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state="paused"))
    wait_until(lambda: panel.images and len(panel.images) >= 2)
    clock.advance(40)
    service.push(snapshot(state="paused", title="Other"))
    clock.advance(20)

    wait_until(lambda: last_view_is(panel, View("paused", "Other", "Artist", position=10, duration=100, volume=35,
                                                queue_position=0, mode="clock", clock="21:48", date="sáb 24 oct")))


def test_idle_clock_disabled(service, display, clock):
    _, panel = display(idle_clock_seconds=None)
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state="stopped"))
    stopped = View("stopped", "Song", "Artist", position=10, duration=100, volume=35, queue_position=0)
    wait_until(lambda: last_view_is(panel, stopped))

    clock.advance(3600)
    time.sleep(0.2)
    assert last_view_is(panel, stopped)


def test_volume_change_shows_popup_for_two_seconds(service, display, clock):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state="paused"))
    paused = View("paused", "Song", "Artist", position=10, duration=100, volume=35, queue_position=0)
    wait_until(lambda: last_view_is(panel, paused))  # el primer snapshot no muestra el indicador

    service.push(snapshot(state="paused", volume=40))
    wait_until(lambda: last_view_is(panel, replace(paused, volume=40, volume_popup=True)))

    clock.advance(1.9)
    time.sleep(0.2)
    assert last_view_is(panel, replace(paused, volume=40, volume_popup=True))
    clock.advance(0.1)
    wait_until(lambda: last_view_is(panel, replace(paused, volume=40)))


def test_same_volume_or_reconnect_does_not_show_popup(service, display):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state="paused"))
    service.push(snapshot(state="paused", title="Other"))
    other = View("paused", "Other", "Artist", position=10, duration=100, volume=35, queue_position=0)
    wait_until(lambda: last_view_is(panel, other))

    service.drop()
    wait_until(lambda: len(service.subscriptions) == 2, timeout=2.5)
    service.push(snapshot(state="paused", volume=50))  # primer snapshot de la conexión nueva

    wait_until(lambda: last_view_is(panel, replace(other, title="Song", volume=50)))
    assert not any(img == render(replace(other, title="Song", volume=50, volume_popup=True)).tobytes()
                   for img in panel.images)


# Desplazamiento del título (SPEC 18)

LONG = "A very long song title that never ends at all"


@pytest.mark.parametrize("elapsed, expected", [
    (0, 0), (SCROLL_PAUSE, 0), (SCROLL_PAUSE + 1, SCROLL_SPEED), (SCROLL_PAUSE + 100 / SCROLL_SPEED, 100),  # 100 = tope
    (SCROLL_PAUSE + 100 / SCROLL_SPEED + 0.9, 100),  # pausa al final
    (2 * SCROLL_PAUSE + 100 / SCROLL_SPEED + 0.1, 0),  # vuelve al inicio
])
def test_scroll_offset(elapsed, expected):
    assert scroll_offset(elapsed, 100) == expected


def test_long_title_scrolls_pauses_and_returns(service, display, clock):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(title=LONG))
    start = replace(PLAYING, title=LONG)
    wait_until(lambda: last_view_is(panel, start))
    end = title_overflow(LONG)
    travel = end / SCROLL_SPEED

    clock.advance(SCROLL_PAUSE + 1)
    wait_until(lambda: last_view_is(panel, replace(start, position=12, scroll=SCROLL_SPEED)))
    clock.advance(travel)
    wait_until(lambda: panel.shows(replace(start, position=12 + int(travel), scroll=end)))
    clock.advance(SCROLL_PAUSE)
    wait_until(lambda: last_view_is(panel, replace(start, position=12 + int(travel + SCROLL_PAUSE), scroll=0)))


@pytest.mark.parametrize("state", ["paused", "stopped"])
def test_long_title_does_not_scroll_when_not_playing(service, display, clock, state):
    _, panel = display(idle_clock_seconds=None)
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state=state, title=LONG))
    wait_until(lambda: last_view_is(panel, View(state, LONG, "Artist", position=10, duration=100, volume=35,
                                                queue_position=0)))
    count = len(panel.images)

    clock.advance(3)
    time.sleep(0.2)
    assert len(panel.images) == count


def test_new_snapshot_with_same_title_keeps_scrolling(service, display, clock):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(title=LONG))
    wait_until(lambda: last_view_is(panel, replace(PLAYING, title=LONG)))
    clock.advance(SCROLL_PAUSE + 1)

    service.push(snapshot(title=LONG, position=11, volume=35))  # p. ej. un seek: no reinicia el desplazamiento
    wait_until(lambda: last_view_is(panel, replace(PLAYING, title=LONG, position=11, scroll=SCROLL_SPEED)))


def test_scrolling_uses_fast_tick_and_short_title_does_not(service, display):
    _, panel = display(tick_seconds=1.0, real_clock=True)
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(title="Song"))
    wait_until(lambda: panel.shows(PLAYING))
    count = len(panel.images)
    time.sleep(0.5)
    assert len(panel.images) <= count + 1  # a lo sumo el cambio de segundo

    service.push(snapshot(title=LONG))
    time.sleep(SCROLL_PAUSE + 0.6)
    assert len(panel.images) >= count + 4  # ~0,1 s por cuadro mientras se desplaza
