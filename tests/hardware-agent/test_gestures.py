import pytest

from gestures import Gestures


class Recorder:
    def __init__(self):
        self.events = []  # ("send", nombre) | ("toast", texto)
        self.menu = False  # menú abierto (SPEC 21)
        self.gestures = Gestures(lambda name: self.events.append(("send", name)),
                                 lambda text: self.events.append(("toast", text)),
                                 hold=0.6, shutdown_hold=3, menu_open=lambda: self.menu)

    def sent(self):
        return [value for kind, value in self.events if kind == "send"]

    def toasts(self):
        return [value for kind, value in self.events if kind == "toast"]

    def run(self, name, until, step=0.05):
        """Aprieta en t=0, hace tick cada step hasta until y suelta."""
        self.gestures.press(name, 0)
        t = 0
        while t + step <= until + 1e-9:
            t = round(t + step, 6)
            self.gestures.tick(t)
        self.gestures.release(name, until)


@pytest.fixture
def rec():
    return Recorder()


@pytest.mark.parametrize("name", ["next", "previous", "play_pause", "menu"])
def test_short_press_sends_once_on_release(rec, name):
    rec.gestures.press(name, 0)
    rec.gestures.tick(0.3)
    assert rec.events == []

    rec.gestures.release(name, 0.4)
    assert rec.events == [("send", name)]


@pytest.mark.parametrize("name", ["volume_up", "volume_down"])
def test_volume_sends_on_press_not_on_release(rec, name):
    rec.gestures.press(name, 0)
    assert rec.sent() == [name]

    rec.gestures.release(name, 0.2)
    assert rec.sent() == [name]


@pytest.mark.parametrize("name, command, text", [("next", "seek_forward", "+10 s"),
                                                 ("previous", "seek_backward", "−10 s")])
def test_held_seek_repeats_every_half_second_without_short_action(rec, name, command, text):
    rec.run(name, until=1.7)  # seek a 0.6, 1.1 y 1.6

    assert rec.sent() == [command] * 3
    assert rec.toasts() == [text] * 3


def test_held_seek_starts_right_at_hold(rec):
    rec.gestures.press("next", 0)
    rec.gestures.tick(0.59)
    assert rec.events == []

    rec.gestures.tick(0.6)
    assert rec.sent() == ["seek_forward"]


def test_release_past_hold_before_tick_is_long(rec):
    rec.gestures.press("next", 0)
    rec.gestures.release("next", 0.7)

    assert rec.sent() == ["seek_forward"]


def test_late_tick_does_not_burst(rec):
    rec.gestures.press("next", 0)
    rec.gestures.tick(0.6)
    rec.gestures.tick(3.0)
    rec.gestures.tick(3.05)

    assert rec.sent() == ["seek_forward"] * 2


def test_held_volume_repeats_every_quarter_second(rec):
    rec.run("volume_up", until=1.4)  # al apretar, y luego a 0.6, 0.85, 1.1, 1.35

    assert rec.sent() == ["volume_up"] * 5
    assert rec.toasts() == []


def test_play_pause_counts_down_and_powers_off_once(rec):
    rec.run("play_pause", until=4.0)

    assert rec.sent() == ["power_off"]
    assert rec.toasts() == ["Apagar 3…", "Apagar 2…", "Apagar 1…"]


def test_power_off_fires_at_shutdown_hold(rec):
    rec.gestures.press("play_pause", 0)
    rec.gestures.tick(2.95)
    assert rec.sent() == []

    rec.gestures.tick(3.0)
    rec.gestures.tick(3.5)
    rec.gestures.release("play_pause", 3.6)
    assert rec.sent() == ["power_off"]
    assert rec.toasts()[-1] == "Apagar 1…"  # sin None: la pantalla queda en "Apagando…"


def test_releasing_play_pause_early_cancels_without_play_pause(rec):
    rec.run("play_pause", until=1.9)

    assert rec.sent() == []
    assert rec.toasts() == ["Apagar 3…", "Apagar 2…", None]


def test_held_menu_opens_menu_once_without_toast(rec):
    rec.run("menu", until=2.0)

    assert rec.sent() == ["menu_open"]
    assert rec.toasts() == []


def test_two_buttons_held_at_once_are_independent(rec):
    g = rec.gestures
    g.press("next", 0)
    g.press("volume_down", 0.1)
    g.tick(0.6)   # next mantenido
    g.tick(0.7)   # volume_down mantenido
    g.release("next", 0.8)
    g.tick(0.95)
    g.release("volume_down", 1.0)
    g.press("menu", 1.1)
    g.release("menu", 1.2)

    assert rec.sent() == ["volume_down", "seek_forward", "volume_down", "volume_down", "menu"]


def test_repeated_press_while_down_is_ignored(rec):
    rec.gestures.press("volume_up", 0)
    rec.gestures.press("volume_up", 0.1)
    rec.gestures.release("volume_up", 0.2)
    rec.gestures.release("volume_up", 0.3)

    assert rec.sent() == ["volume_up"]


def test_release_without_press_does_nothing(rec):
    rec.gestures.release("next", 1)
    rec.gestures.tick(2)

    assert rec.events == []


def test_custom_hold_times():
    sent = []
    g = Gestures(sent.append, lambda text: None, hold=0.3, shutdown_hold=1)
    g.press("next", 0)
    g.release("next", 0.35)
    g.press("play_pause", 1)
    g.tick(2)

    assert sent == ["seek_forward", "power_off"]


# Con el menú abierto (SPEC 21)

@pytest.fixture
def menu(rec):
    rec.menu = True
    return rec


@pytest.mark.parametrize("name, local", [("next", "menu_down"), ("previous", "menu_up"),
                                         ("play_pause", "menu_select"), ("menu", "menu_back")])
def test_short_press_in_menu_sends_local_name_on_release(menu, name, local):
    menu.gestures.press(name, 0)
    assert menu.events == []

    menu.gestures.release(name, 0.3)
    assert menu.events == [("send", local)]


@pytest.mark.parametrize("name, local", [("next", "menu_down"), ("previous", "menu_up")])
def test_held_scroll_in_menu_repeats_fast_without_toast(menu, name, local):
    menu.run(name, until=1.0)  # a 0.6, 0.75 y 0.9

    assert menu.sent() == [local] * 3
    assert menu.toasts() == []


def test_held_menu_in_menu_closes(menu):
    menu.run("menu", until=2.0)

    assert menu.sent() == ["menu_close"]


def test_held_play_pause_in_menu_still_powers_off(menu):
    menu.run("play_pause", until=4.0)

    assert menu.sent() == ["power_off"]
    assert menu.toasts() == ["Apagar 3…", "Apagar 2…", "Apagar 1…"]


def test_volume_in_menu_is_unchanged(menu):
    menu.run("volume_down", until=0.9)  # al apretar, y luego a 0.6 y 0.85

    assert menu.sent() == ["volume_down"] * 3


def test_menu_state_is_read_when_each_action_fires(rec):
    g = rec.gestures
    g.press("menu", 0)
    g.tick(0.6)  # abre el menú
    rec.menu = True
    g.release("menu", 0.7)
    g.press("next", 1)
    g.release("next", 1.1)
    g.press("menu", 2)
    rec.menu = False  # se cerró (timeout) mientras estaba apretado
    g.release("menu", 2.1)

    assert rec.sent() == ["menu_open", "menu_down", "menu"]
