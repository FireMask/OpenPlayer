"""Carátula para el modo art (SPEC 19): player.get_cover → bytes → imagen circular de 228x228."""

import base64
import io
import json
import logging

from PIL import Image, ImageDraw, ImageOps

log = logging.getLogger(__name__)

SIZE = 228  # diámetro dentro del anillo de progreso (radio 114)
MAX_LINE_BYTES = 3 * 1024 * 1024  # 2 MB de imagen en base64 (~2,7 MB) más el JSON
TIMEOUT_SECONDS = 5.0


def fetch_cover(connect) -> bytes | None:
    """Pide la carátula de la pista actual en una conexión propia; None si no hay o algo falla."""
    try:
        sock = connect()
    except OSError as e:
        log.warning("cover: cannot connect: %s", e)
        return None
    try:
        sock.settimeout(TIMEOUT_SECONDS)
        sock.sendall(b'{"type":"player.get_cover"}\n')
        data = bytearray()
        while b"\n" not in data:
            chunk = sock.recv(65536)
            if not chunk:
                raise OSError("connection closed")
            data += chunk
            if len(data) > MAX_LINE_BYTES:
                raise OSError("cover line too long")
        message = json.loads(data[:data.index(b"\n")])
    except (OSError, ValueError) as e:
        log.warning("cover: request failed: %s", e)
        return None
    finally:
        sock.close()
    if not isinstance(message, dict) or message.get("type") != "player.cover":
        if isinstance(message, dict) and message.get("type") == "error":
            log.warning("cover: %s", message.get("message"))
        return None
    encoded = message.get("data")
    if not isinstance(encoded, str):
        return None  # la pista no tiene carátula
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError:
        log.warning("cover: invalid base64")
        return None


def prepare(data: bytes) -> Image.Image | None:
    """Imagen → RGB 228x228 recortada al centro, en círculo sobre negro. None si no se puede decodificar."""
    try:
        image = Image.open(io.BytesIO(data))
        if image.format == "JPEG":
            image.draft("RGB", (SIZE, SIZE))  # decodifica ya reducida: mucho más rápido en la Pi Zero
        image = ImageOps.fit(image.convert("RGB"), (SIZE, SIZE), Image.Resampling.BILINEAR)
    except Exception as e:  # Pillow lanza varios tipos según el formato roto
        log.warning("cover: cannot decode image: %s", e)
        return None
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, SIZE - 1, SIZE - 1), fill=255)
    result = Image.new("RGB", (SIZE, SIZE))
    result.paste(image, mask=mask)
    return result
