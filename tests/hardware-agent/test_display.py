import json
import logging
import socket
import threading
import time

import pytest

from display import Display, parse
from screen import View, render


def wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met within timeout")


def snapshot(state="playing", title="Song", artist="Artist", position=10, duration=100, volume=35):
    return {"type": "player.snapshot", "state": state, "trackTitle": title, "trackArtist": artist,
            "positionSeconds": position, "durationSeconds": duration, "volume": volume,
            "queuePosition": 0, "queueVersion": 1}


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
def display(service):
    created = []

    def make(panel=None, tick_seconds=1.0, retry_seconds=0.1):
        panel = panel or FakePanel()
        d = Display("/x.sock", panel, connect=service.connect, tick_seconds=tick_seconds, retry_seconds=retry_seconds)
        d.start()
        created.append(d)
        return d, panel

    yield make
    for d in created:
        d.stop()


PLAYING = View("playing", "Song", "Artist", position=10, duration=100, volume=35)


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
    service.push(snapshot(state="paused", title="Other", volume=40))

    wait_until(lambda: panel.shows(View("paused", "Other", "Artist", position=10, duration=100, volume=40)))


def test_same_view_does_not_redraw(service, display):
    _, panel = display(tick_seconds=0.05)
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state="paused"))
    wait_until(lambda: panel.shows(View("paused", "Song", "Artist", position=10, duration=100, volume=35)))
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
    wait_until(lambda: panel.shows(View("playing", "Back", "Artist", position=10, duration=100, volume=35)))


def test_starts_offline_without_service(service, display):
    service.available = False
    _, panel = display()

    wait_until(lambda: panel.shows(View("offline")))


def test_error_line_shows_mpd_error(service, display):
    _, panel = display()
    wait_until(lambda: service.subscriptions)
    service.push({"type": "error", "request": "player.get_snapshot", "message": "MPD unavailable"})

    wait_until(lambda: panel.shows(View("mpd_error")))


def test_position_advances_while_playing(service, display):
    _, panel = display(tick_seconds=0.05)
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(position=10))

    wait_until(lambda: panel.shows(View("playing", "Song", "Artist", position=12, duration=100, volume=35)))


def test_position_stops_at_duration(service, display):
    _, panel = display(tick_seconds=0.02)
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(position=98, duration=100))
    wait_until(lambda: panel.shows(View("playing", "Song", "Artist", position=100, duration=100, volume=35)))
    count = len(panel.images)
    time.sleep(0.2)  # 10 ticks: la vista queda en 100 y no se redibuja

    assert len(panel.images) == count


@pytest.mark.parametrize("state", ["paused", "stopped"])
def test_position_does_not_advance_when_not_playing(service, display, state):
    _, panel = display(tick_seconds=0.05)
    wait_until(lambda: service.subscriptions)
    service.push(snapshot(state=state, position=10))
    wait_until(lambda: panel.shows(View(state, "Song", "Artist", position=10, duration=100, volume=35)))
    time.sleep(0.3)

    assert not panel.shows(View(state, "Song", "Artist", position=11, duration=100, volume=35))


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
