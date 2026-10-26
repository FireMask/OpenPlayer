import pytest

from menu import Menu


def page(entries, total=None, offset=0):
    return {"type": "library.page", "offset": offset, "total": len(entries) if total is None else total,
            "entries": entries}


def folder(uri):
    return {"uri": uri, "directory": True}


def track(uri, title=None):
    return {"uri": uri, "directory": False, "title": title, "artist": None, "album": None, "durationSeconds": None}


OK = {"type": "ok"}


class Service:
    """request() falso: responde según una función del pedido y los guarda. run diferido si deferred."""

    def __init__(self, answer, *, deferred=False):
        self.answer = answer
        self.requests = []
        self.toasts = []
        self.changes = 0
        self.powered_off = 0
        self.jobs = []
        self.now = 0.0
        self.queue_position = None
        self.menu = Menu(self.request, power_off=self.power_off, toast=self.toasts.append, changed=self.changed,
                         queue_position=lambda: self.queue_position,
                         run=self.jobs.append if deferred else (lambda job: job()),
                         monotonic=lambda: self.now)

    def request(self, message):
        self.requests.append(message)
        return self.answer(message)

    def power_off(self):
        self.powered_off += 1

    def changed(self):
        self.changes += 1

    def view(self):
        return self.menu.view(self.now)

    def rows(self):
        return list(self.view().rows)

    def go(self, *labels):
        """Elige cada etiqueta en orden, moviendo el cursor hasta ella."""
        for label in labels:
            rows = self.rows()
            target = rows.index(label)
            while self.view().cursor < target:
                self.menu.down()
            while self.view().cursor > target:
                self.menu.up()
            self.menu.select()


LIBRARY = {
    "": page([folder("Rock"), track("loose.mp3")]),
    "Rock": page([folder("Rock/AC DC"), track("Rock/x.flac", "X")]),
}


def library(message):
    kind = message["type"]
    if kind == "library.browse":
        return LIBRARY[message["path"]]
    if kind == "playlist.list":
        return {"type": "playlist.list", "playlists": ["Viaje", "Gym"]}
    if kind == "playlist.get":
        return page([track("a.flac", "A"), track("b.flac", "B"), track("c.flac")], offset=message["offset"])
    if kind == "queue.get":
        return {"type": "queue.page", "offset": 0, "total": 2,
                "entries": [{**track("q1.flac", "Q1"), "id": 1}, {**track("q2.flac", "Q2"), "id": 2}]}
    return OK


@pytest.fixture
def svc():
    s = Service(library)
    s.menu.open()
    return s


def test_closed_menu_has_no_view_and_ignores_buttons():
    s = Service(library)
    s.menu.down()
    s.menu.select()
    s.menu.back()

    assert s.view() is None
    assert not s.menu.is_open
    assert s.requests == []


def test_root(svc):
    assert svc.menu.is_open
    assert svc.view().title == "Menú"
    assert svc.rows() == ["Biblioteca", "Listas", "Cola", "Apagar"]
    assert svc.view().cursor == 0


def test_library_root_has_no_play_all_and_labels_folders_and_files(svc):
    svc.go("Biblioteca")

    assert svc.view().title == "Biblioteca"
    assert svc.rows() == ["Rock", "loose.mp3"]
    assert svc.requests == [{"type": "library.browse", "path": "", "offset": 0}]


def test_folder_has_play_all_first(svc):
    svc.go("Biblioteca", "Rock")

    assert svc.view().title == "Rock"
    assert svc.rows() == ["▶ Reproducir todo", "AC DC", "X"]


@pytest.mark.parametrize("path, label, uri", [
    (("Rock", "X"), "X", "Rock/x.flac"),
    (("Rock", "▶ Reproducir todo"), "Rock", "Rock"),
])
def test_track_actions_send_the_right_message(path, label, uri):
    for action, message, closes in [
        ("Reproducir", {"type": "library.play", "uri": uri}, True),
        ("Siguiente", {"type": "queue.add", "uri": uri, "next": True}, False),
        ("Agregar a la cola", {"type": "queue.add", "uri": uri, "next": False}, False),
    ]:
        s = Service(library)
        s.menu.open()
        s.go("Biblioteca", *path)
        assert s.view().title == label
        assert s.rows() == ["Reproducir", "Siguiente", "Agregar a la cola"]

        s.go(action)
        assert s.requests[-1] == message
        if closes:
            assert s.view() is None and s.toasts == []
        else:
            assert s.view().title == label and s.toasts == ["Agregado"]


def test_playlists_play_list_and_play_from_track(svc):
    svc.go("Listas")
    assert svc.rows() == ["Viaje", "Gym"]

    svc.go("Viaje")
    assert svc.view().title == "Viaje"
    assert svc.rows() == ["▶ Reproducir lista", "A", "B", "c.flac"]
    assert svc.requests[-1] == {"type": "playlist.get", "name": "Viaje", "offset": 0}

    svc.go("c.flac")
    assert svc.rows() == ["Reproducir desde aquí"]
    svc.go("Reproducir desde aquí")
    assert svc.requests[-1] == {"type": "playlist.play", "name": "Viaje", "position": 2}
    assert svc.view() is None


def test_play_whole_playlist(svc):
    svc.go("Listas", "Gym", "▶ Reproducir lista")

    assert svc.requests[-1] == {"type": "playlist.play", "name": "Gym", "position": 0}
    assert svc.view() is None


def test_queue_marks_current_and_plays_position(svc):
    svc.queue_position = 1
    svc.go("Cola")

    assert svc.rows() == ["Q1", "♪ Q2"]
    svc.go("Q1")
    assert svc.requests[-1] == {"type": "queue.play", "position": 0}
    assert svc.view() is None


def test_power_off_asks_with_no_by_default(svc):
    svc.go("Apagar")
    assert svc.view().title == "¿Apagar?"
    assert svc.rows() == ["No", "Sí"]
    assert svc.view().cursor == 0

    svc.menu.select()  # No
    assert svc.view().title == "Menú"
    assert svc.powered_off == 0

    svc.go("Apagar", "Sí")
    assert svc.powered_off == 1
    assert svc.view() is None


def test_cursor_does_not_wrap(svc):
    svc.menu.up()
    assert svc.view().cursor == 0

    for _ in range(10):
        svc.menu.down()
    assert svc.view().cursor == 3


def test_back_goes_up_one_level_and_closes_at_root(svc):
    svc.go("Biblioteca", "Rock")
    svc.menu.back()
    assert svc.view().title == "Biblioteca"
    assert svc.view().cursor == 0  # el cursor del nivel quedó donde estaba ("Rock")

    svc.menu.back()
    assert svc.view().title == "Menú"
    assert svc.view().cursor == 0
    svc.menu.back()
    assert svc.view() is None


def test_close_from_any_level(svc):
    svc.go("Biblioteca", "Rock")
    svc.menu.close()

    assert svc.view() is None
    assert not svc.menu.is_open


def test_times_out_after_30_s_without_buttons(svc):
    svc.now = 29
    svc.menu.down()  # renueva
    svc.now = 58.9
    assert svc.view() is not None

    svc.now = 59
    assert not svc.menu.is_open
    assert svc.view() is None
    svc.menu.select()  # ya cerrado: no hace nada
    assert svc.requests == []


def big_folder(message):
    if message["type"] != "library.browse":
        return OK
    if message["path"] == "":
        return page([folder("Big")])
    offset = message["offset"]
    count = min(100, 250 - offset)
    return page([track(f"Big/{i}.mp3") for i in range(offset, offset + count)], total=250, offset=offset)


def test_next_page_is_requested_near_the_end_once_and_reaches_the_last():
    s = Service(big_folder)
    s.menu.open()
    s.go("Biblioteca", "Big")
    assert len(s.rows()) == 101  # "Reproducir todo" + 100

    for _ in range(89):
        s.menu.down()
    assert [r.get("offset") for r in s.requests] == [0, 0]  # cursor 89: 11 filas debajo

    s.menu.down()  # cursor 90: 10 filas debajo
    s.menu.down()
    assert [r.get("offset") for r in s.requests] == [0, 0, 100]
    assert len(s.rows()) == 201

    for _ in range(300):
        s.menu.down()
    assert [r.get("offset") for r in s.requests] == [0, 0, 100, 200]
    assert s.rows()[-1] == "249.mp3"
    assert s.view().cursor == 250


def test_page_is_not_requested_twice_while_loading():
    s = Service(big_folder, deferred=True)
    s.menu.open()
    s.menu.select()  # Biblioteca
    s.jobs.pop()()
    s.menu.select()  # Big
    s.jobs.pop()()

    for _ in range(95):
        s.menu.down()
    assert len(s.jobs) == 1  # una sola página pedida, todavía sin respuesta
    s.jobs.pop()()
    assert len(s.rows()) == 201


def test_loading_level_shows_loading_and_buttons_still_respond():
    s = Service(library, deferred=True)
    s.menu.open()
    s.menu.select()  # Biblioteca, sin respuesta

    assert s.view().title == "Biblioteca"
    assert s.view().loading and s.view().rows == ()
    s.menu.down()  # sin filas: no hace nada ni falla
    s.jobs.pop()()
    assert not s.view().loading
    assert s.rows() == ["Rock", "loose.mp3"]


def test_failed_level_shows_error_and_stays_on_same_level_and_row(svc):
    svc.answer = lambda message: None
    svc.menu.down()
    svc.menu.select()  # Listas

    assert svc.toasts == ["Error"]
    assert svc.view().title == "Menú"
    assert svc.view().cursor == 1


@pytest.mark.parametrize("reply", [{"type": "ok"}, {"type": "library.page", "entries": "x", "total": 1}])
def test_reply_with_wrong_shape_is_an_error(svc, reply):
    svc.answer = lambda message: reply
    svc.menu.select()

    assert svc.toasts == ["Error"]
    assert svc.view().title == "Menú"


def test_failed_action_shows_error_and_stays(svc):
    svc.go("Biblioteca", "loose.mp3")
    svc.answer = lambda message: None
    svc.go("Reproducir")

    assert svc.toasts == ["Error"]
    assert svc.view().title == "loose.mp3"
    assert svc.view().cursor == 0


def test_failed_next_page_shows_error_and_keeps_rows():
    s = Service(big_folder)
    s.menu.open()
    s.go("Biblioteca", "Big")
    s.answer = lambda message: None
    for _ in range(95):
        s.menu.down()

    assert s.toasts and set(s.toasts) == {"Error"}  # reintenta en el próximo movimiento
    assert len(s.rows()) == 101
    assert s.view().title == "Big"


def test_late_reply_for_a_level_already_left_is_discarded():
    s = Service(library, deferred=True)
    s.menu.open()
    s.menu.select()  # Biblioteca, sin respuesta
    s.menu.back()
    changes = s.changes

    s.jobs.pop()()
    assert s.view().title == "Menú"
    assert s.rows() == ["Biblioteca", "Listas", "Cola", "Apagar"]
    assert s.changes == changes
    assert s.toasts == []


def test_late_error_for_a_level_already_left_shows_nothing():
    s = Service(lambda message: None, deferred=True)
    s.menu.open()
    s.menu.select()
    s.menu.close()
    s.jobs.pop()()

    assert s.toasts == []
    assert s.view() is None


def test_changed_is_called_on_each_visible_change(svc):
    start = svc.changes
    svc.menu.down()
    svc.menu.up()
    svc.menu.up()  # en el primero: no cambia

    assert svc.changes == start + 2
