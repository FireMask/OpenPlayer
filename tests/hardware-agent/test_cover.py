import base64
import io
import json
import socket
import threading

import pytest
from PIL import Image

from cover import SIZE, fetch_cover, prepare


def encoded(image, fmt):
    buffer = io.BytesIO()
    image.save(buffer, fmt)
    return buffer.getvalue()


def serve(reply: bytes, received=None):
    """connect() falso: un socketpair cuyo otro extremo lee el pedido y responde reply."""
    def connect():
        client, server = socket.socketpair()

        def answer():
            line = server.makefile("rb").readline()
            if received is not None:
                received.append(line)
            server.sendall(reply)
            server.close()
        threading.Thread(target=answer, daemon=True).start()
        return client
    return connect


def cover_line(data, mime="image/jpeg"):
    payload = base64.b64encode(data).decode() if data is not None else None
    return (json.dumps({"type": "player.cover", "songId": 17, "mime": mime, "data": payload}) + "\n").encode()


# fetch_cover

def test_fetch_returns_decoded_bytes_and_sends_request():
    data = bytes(range(256)) * 4000  # ~1 MB: varios recv
    received = []

    assert fetch_cover(serve(cover_line(data), received)) == data
    assert received == [b'{"type":"player.get_cover"}\n']


@pytest.mark.parametrize("reply", [
    cover_line(None),
    b'{"type":"error","request":"player.get_cover","message":"cover too large"}\n',
    b'{"type":"player.cover","songId":1,"mime":null,"data":"not base64!"}\n',
    b"not json\n",
    b"[1]\n",
    b'{"type":"player.cover"',  # se corta sin \n
])
def test_fetch_returns_none_on_no_cover_or_bad_reply(reply):
    assert fetch_cover(serve(reply)) is None


def test_fetch_returns_none_when_service_is_down():
    def refused():
        raise ConnectionRefusedError("down")

    assert fetch_cover(refused) is None


def test_fetch_rejects_line_over_limit(monkeypatch):
    import cover
    monkeypatch.setattr(cover, "MAX_LINE_BYTES", 1000)

    assert fetch_cover(serve(cover_line(bytes(2000)))) is None


# prepare

def gradient(width, height):
    image = Image.new("RGB", (width, height))
    image.putdata([(x * 255 // width, y * 255 // height, 128) for y in range(height) for x in range(width)])
    return image


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
def test_prepare_scales_to_circle(fmt):
    image = prepare(encoded(gradient(600, 600), fmt))

    assert image.mode == "RGB" and image.size == (SIZE, SIZE)
    assert image.getpixel((0, 0)) == (0, 0, 0)  # esquina fuera del círculo
    assert image.getpixel((SIZE // 2, SIZE // 2)) != (0, 0, 0)


def test_prepare_crops_center_without_distortion():
    # Imagen ancha: rojo a los costados, verde en el cuadrado central.
    wide = Image.new("RGB", (900, 300), (255, 0, 0))
    wide.paste((0, 255, 0), (300, 0, 600, 300))

    image = prepare(encoded(wide, "PNG"))

    assert image.getpixel((SIZE // 2, SIZE // 2)) == (0, 255, 0)
    assert image.getpixel((5, SIZE // 2)) == (0, 255, 0)  # el borde del círculo también es del centro


def test_prepare_accepts_palette_and_alpha_png():
    rgba = Image.new("RGBA", (100, 100), (10, 20, 30, 128))

    assert prepare(encoded(rgba, "PNG")).size == (SIZE, SIZE)


@pytest.mark.parametrize("data", [b"", b"not an image", encoded(gradient(50, 50), "JPEG")[:100]])
def test_prepare_returns_none_for_corrupt_data(data):
    assert prepare(data) is None
