# SPEC 17 — Pantalla redonda GC9A01 240x240

> **Status:** Approved
> **Depends on:** SPEC 05, SPEC 16
> **Date:** 2026-10-24
> **Objective:** Que el hardware agent muestre la pista actual (título, artista, estado, anillo de progreso y volumen) en una pantalla redonda GC9A01 de 1,28" por SPI, alimentada por `player.subscribe`, sin afectar a los botones si la pantalla falla o no está.

## Scope

**In:**

- `src/hardware-agent/`, solo con stdlib, `gpiozero`, Pillow (`python3-pil`) y `spidev` (`python3-spidev`):
  - `config.py`: sección opcional `hardware.display`.
    - Si falta o tiene `enabled: false`, no hay pantalla y el agente se comporta igual que hoy.
    - Validación: `spiBus` y `spiDevice` 0–1; `dc` y `rst` pines BCM 0–27, sin repetirse entre sí ni con los botones; `spiHz` entre 1 000 000 y 62 500 000; `rotation` en 0, 90, 180 o 270.
    - Si algo es inválido, `ConfigError` nombrando el campo (exit 1, como hoy).
  - `gc9a01.py`: driver mínimo. Secuencia de init del GC9A01, `show(image)` que manda el cuadro completo 240x240 en RGB565 por SPI. DC y RST con `gpiozero.DigitalOutputDevice`. El objeto SPI es inyectable para probarlo en Windows.
  - `screen.py`: `render(view) -> PIL.Image` puro, sin hardware.
    - Reproduciendo o en pausa: título, artista, ícono de estado (▶ / ⏸), anillo de progreso por el borde y volumen.
    - Detenido sin pista: "Detenido".
    - Service caído: "Sin conexión".
    - Línea de error de MPD: "MPD no responde".
    - Títulos y artistas largos se cortan con "…" para entrar en el círculo.
    - Fuente DejaVu Sans de `fonts-dejavu-core`.
  - `display.py`: hilo de la pantalla.
    - Suscripción propia (`player.subscribe`) en una segunda conexión al socket, con reintento cada 2 s.
    - Mientras está `playing`, avanza la posición localmente una vez por segundo; cada push la corrige.
    - Redibuja solo cuando cambia lo que se ve.
    - Si el init de la pantalla falla, un `error` en el log y el hilo termina; los botones siguen.
  - `main.py`: arranca el hilo de la pantalla si está habilitada y lo detiene con SIGTERM o Ctrl+C.
  - `requirements-dev.txt`: Pillow con la versión de `python3-pil` en Pi OS.
- `tests/hardware-agent/`:
  - `test_config.py`: sección ausente o deshabilitada, válida, y cada caso inválido.
  - `test_gc9a01.py`: con SPI falso, el init manda la secuencia esperada y `show()` manda CASET/RASET/RAMWR más 115 200 bytes RGB565 big-endian.
  - `test_screen.py`: cada estado renderiza una imagen 240x240 sin error; título largo se corta; anillo proporcional a la posición.
  - `test_display.py`: con el Service falso por TCP, el snapshot llega a `render`, el Service caído muestra "Sin conexión" y reconecta, y el avance local corre solo en `playing`.
- `deploy/openplayer-hardware.service`: `SupplementaryGroups=gpio spi`.
- `deploy/install.sh`:
  - verifica `python3-pil`, `python3-spidev` y `fonts-dejavu-core` (no los instala);
  - si falta `/dev/spidev0.0`, warning con `sudo raspi-config nonint do_spi 0` (no falla: la pantalla puede estar deshabilitada).
- `config/player.example.json`: `hardware.display` (con `enabled: false`) reemplaza a `oledEnabled`.
- Documentación: reemplazar el plan de OLED SSD1306 I²C por esta pantalla en `architecture.md`, `gpio-map.md` (cableado SPI) y `assembly.md` §11, más el README.

**Out of scope (para futuras specs):**

- Carátula del álbum.
- Menú y navegación con el botón `menu`.
- Texto con desplazamiento (marquee).
- Apagar o dormir la pantalla por inactividad (no hay pin BL; `DISPOFF` queda para después).
- Redibujo parcial, DMA o framebuffer del kernel (`panel-mipi-dbi`).
- Pantalla de arranque antes de que responda el Service.
- Brillo o tema configurables.
- Cambios en el Service C# o en el contrato IPC.
- Habilitar SPI o instalar paquetes desde `install.sh`.

## Data model

Archivos:

```text
src/hardware-agent/
  config.py         // + DisplayConfig, AgentConfig.display
  gc9a01.py         // GC9A01 (driver)
  screen.py         // View, render()
  display.py        // Display (hilo: suscripción + avance local + dibujo)
  main.py           // arranca/detiene Display
  requirements-dev.txt  // + Pillow==11.1.0 (python3-pil de la Pi, Pi OS trixie)
tests/hardware-agent/
  test_config.py    // + casos de display
  test_gc9a01.py
  test_screen.py
  test_display.py
```

Cableado (módulo de 7 pines, sin BL; 3.3 V tanto en alimentación como en lógica):

| Módulo | Pi | Pin físico |
|---|---|---|
| VCC | 3.3 V | 17 |
| GND | GND | 20 |
| SCL | GPIO11 / SPI0 SCLK | 23 |
| SDA | GPIO10 / SPI0 MOSI | 19 |
| CS | GPIO8 / SPI0 CE0 | 24 |
| DC | GPIO5 | 29 |
| RST | GPIO6 | 31 |

`player.json` (`hardware.oledEnabled` desaparece):

```json
"display": {
  "enabled": false,
  "spiBus": 0,
  "spiDevice": 0,
  "dc": 5,
  "rst": 6,
  "spiHz": 40000000,
  "rotation": 180
}
```

Python:

```python
@dataclass(frozen=True)
class DisplayConfig:
    spi_bus: int
    spi_device: int
    dc: int          # BCM
    rst: int         # BCM
    spi_hz: int
    rotation: int    # 0 | 90 | 180 | 270

@dataclass(frozen=True)
class AgentConfig:
    socket_path: str
    pins: dict
    debounce_seconds: float
    display: DisplayConfig | None   # None: sección ausente o enabled=false

# screen.py
WIDTH = HEIGHT = 240

@dataclass(frozen=True)
class View:
    status: str            # "playing" | "paused" | "stopped" | "offline" | "mpd_error"
    title: str | None = None
    artist: str | None = None
    position: int | None = None   # segundos
    duration: int | None = None
    volume: int | None = None

def render(view: View) -> Image.Image: ...   # RGB 240x240

# gc9a01.py
class GC9A01:
    def __init__(self, spi, dc, rst, *, spi_hz: int, rotation: int): ...
        # spi: objeto con xfer3/writebytes2 (spidev.SpiDev o falso en pruebas); dc/rst: DigitalOutputDevice
    def init(self) -> None: ...                  # reset por RST + secuencia de init + DISPON
    def show(self, image: Image.Image) -> None: ...  # rota según rotation, CASET/RASET 0–239, RAMWR, 115 200 bytes RGB565 BE

# display.py
class Display:
    def __init__(self, socket_path: str, panel, *, connect=None, tick_seconds=1.0, retry_seconds=2.0): ...
        # panel: algo con show(image); connect inyectable igual que Sender (TCP en pruebas)
    def start(self) -> None: ...   # hilo daemon: panel.init() y bucle
    def stop(self) -> None: ...
```

Snapshot → `View` (campos de SPEC 03/16, sin cambios):

| Línea recibida | `View` |
|---|---|
| `player.snapshot` con `state` `playing` / `paused` | `status` = `state`; título, artista, posición, duración y volumen de la línea |
| `player.snapshot` con `stopped` | `"stopped"` (con pista si `trackTitle` no es null; si no, "Detenido") |
| `{"type":"error",...}` | `"mpd_error"` → "MPD no responde" |
| Conexión caída o rechazada | `"offline"` → "Sin conexión" |

Disposición inicial (ajustable al implementar, verificada a ojo en la Pi):

- Fondo negro.
- Anillo de progreso: radio 114 px, 6 px de grosor, desde las 12 en sentido horario, con la pista en gris.
- Ícono de estado arriba (y≈60).
- Título 22 px blanco (y≈105).
- Artista 16 px gris (y≈135).
- Volumen abajo, `Vol 35` (y≈180).
- El texto se corta con "…" al ancho útil del círculo en esa altura.

Logs:

```text
info: display ready (spi0.0, 40000000 Hz)
error: display init failed: <motivo>
warning: display: disconnected from /run/openplayer/hardware.sock
```

## Implementation plan

1. **Config.**
   - `DisplayConfig` en `config.py`, con `hardware.display` opcional, y `player.example.json` (`display` reemplaza a `oledEnabled`).
   - Pruebas en `test_config.py`: sección ausente → `None`; `enabled: false` → `None`; válida; cada campo inválido; `dc`/`rst` repetidos entre sí o con un botón.
   - Verificar: `pytest tests/hardware-agent` en verde; el agente arranca igual que hoy con el ejemplo.
2. **Render.**
   - `screen.py` (`View`, `render`) y `Pillow==11.1.0` en `requirements-dev.txt`.
   - `test_screen.py`: los 5 estados devuelven RGB 240x240; título largo cortado con "…"; anillo al 50 % pinta píxeles del lado derecho y ninguno del izquierdo; sin duración, no hay anillo.
   - Verificar: guardar los 5 PNG en el scratchpad y mirarlos.
3. **Driver.**
   - `gc9a01.py` con SPI, DC y RST inyectables.
   - `test_gc9a01.py` con SPI falso y `MockFactory`:
     - el init pulsa RST y manda la secuencia del GC9A01 terminada en `DISPON` (0x29);
     - `show()` manda CASET/RASET 0–239 y `RAMWR`, con DC en alto para los datos y 115 200 bytes en RGB565 big-endian;
     - un píxel rojo puro se codifica como `0xF800`;
     - `rotation` 180 invierte la imagen.
4. **Hilo de la pantalla.**
   - `display.py` con `connect` inyectable, suscripción, reintento cada 2 s, avance local y redibujo solo si cambia la `View`.
   - `test_display.py` con el Service falso por TCP y un panel falso que guarda las imágenes:
     - el snapshot inicial llega al panel;
     - un push nuevo redibuja;
     - el Service caído muestra "Sin conexión" y reconecta;
     - la línea de error muestra "MPD no responde";
     - en `playing`, la posición avanza con el tick (intervalo corto inyectable); en `paused`, no;
     - si `panel.init()` lanza, el hilo termina con un `error` en el log;
     - `stop()` termina el hilo.
5. **`main.py`.**
   - Con `display` habilitada, importa `spidev` y `gc9a01` adentro de un `try`.
   - Cualquier error de import o de hardware → `error` en el log, sin pantalla, y los botones siguen.
   - SIGTERM o Ctrl+C → `display.stop()`.
   - Verificar en Windows con `GPIOZERO_PIN_FACTORY=mock`: con `enabled: true` y sin `spidev`, registra el error y sigue; Ctrl+C sale con 0.
6. **Deploy.**
   - Unidad con `SupplementaryGroups=gpio spi`.
   - `install.sh`: verifica `python3-pil`, `python3-spidev` y `fonts-dejavu-core`; warning si falta `/dev/spidev0.0`.
   - Verificar: `deploy.ps1` → exit 0 con la pantalla deshabilitada.
7. **Docs.**
   - `architecture.md`: §1–§5 (la pantalla reemplaza a la OLED; el agente se suscribe), §10 (`hardware.display`) y §13 (fase).
   - `gpio-map.md`: tabla SPI (reemplaza las filas OLED I²C), activar SPI y conflictos.
   - `assembly.md` §11: montaje y prueba.
   - README: cómo habilitar la pantalla y ver sus logs.
8. **En la Pi.** Cablear según la tabla, `raspi-config nonint do_spi 0`, `enabled: true` en `/opt/openplayer/player.json`, reiniciar `openplayer-hardware` y recorrer los criterios manuales. Si hace falta, ajustar `spiHz` y `rotation` y documentar los valores finales.

## Acceptance criteria

**Windows (automatizable):**

- [ ] `pytest tests/hardware-agent` pasa todas las pruebas.
- [ ] Sin `hardware.display` o con `enabled: false`, `AgentConfig.display` es `None` y el agente no importa `spidev` ni Pillow.
- [ ] `config.py` rechaza con `ConfigError`, nombrando el campo:
  - `spiBus`/`spiDevice` fuera de 0–1;
  - `dc`/`rst` fuera de 0–27, no enteros, repetidos entre sí o con un botón;
  - `spiHz` fuera de 1 000 000–62 500 000;
  - `rotation` distinto de 0/90/180/270.
- [ ] `render()` devuelve una imagen RGB 240x240 para `playing`, `paused`, `stopped`, `offline` y `mpd_error`.
- [ ] Un título más ancho que el círculo se dibuja cortado y terminado en "…".
- [ ] El anillo cubre una fracción proporcional a `position / duration`; sin `duration` no hay anillo.
- [ ] `show()` manda CASET/RASET 0–239, `RAMWR` y exactamente 115 200 bytes; un píxel `(255,0,0)` se codifica como `0xF800`.
- [ ] El init termina en `DISPON` (0x29) tras pulsar RST.
- [ ] `Display` dibuja el snapshot inicial, redibuja con cada push que cambia la vista y no redibuja si la vista no cambió.
- [ ] Con el Service caído, `Display` dibuja "Sin conexión" y vuelve a suscribirse en 2 s cuando el Service vuelve.
- [ ] Una línea `error` dibuja "MPD no responde".
- [ ] En `playing`, la posición avanza 1 s por tick; en `paused` y `stopped`, no.
- [ ] Si `panel.init()` falla, se registra un `error`, el hilo termina y los botones siguen enviando `button.pressed`.
- [ ] El agente solo importa stdlib, `gpiozero`, `PIL` y `spidev` (verificable con grep).
- [ ] `dotnet build` y `dotnet test` siguen pasando.

**Raspberry Pi (manual):**

- [ ] Con `enabled: false` y sin pantalla, `deploy.ps1` termina con exit 0 y el agente se comporta igual que en SPEC 05.
- [ ] Con la pantalla cableada, SPI activo y `enabled: true`, `journalctl -u openplayer-hardware` muestra `display ready` y la pantalla dibuja título, artista, estado, anillo y volumen de la pista actual.
- [ ] `mpc next` cambia título y artista en la pantalla en menos de 1 s.
- [ ] Botón de volumen (o `mpc volume 40`): el volumen en pantalla cambia en menos de 1 s.
- [ ] Play/pausa cambia el ícono en menos de 1 s; en pausa el anillo no avanza.
- [ ] Durante la reproducción, el anillo avanza de forma continua y coincide con `mpc status` con 2 s de diferencia o menos.
- [ ] `sudo systemctl stop openplayer` → la pantalla muestra "Sin conexión"; al iniciarlo, vuelve a la pista en 5 s o menos.
- [ ] Con RST desconectado o `spiDevice` erróneo, los botones siguen funcionando y el log muestra el error de la pantalla.
- [ ] La imagen no aparece espejada ni con colores invertidos (rojo se ve rojo); si hace falta, `rotation` y `spiHz` se ajustan y los valores finales quedan documentados.
- [ ] Tras `sudo reboot`, la pantalla muestra la pista sin intervención.

**Documentación:**

- [ ] `architecture.md`, `gpio-map.md` y `assembly.md` §11 describen la GC9A01 por SPI y ya no mencionan la OLED SSD1306 I²C como plan.
- [ ] `gpio-map.md` tiene la tabla de cableado y cómo activar SPI.
- [ ] El README explica cómo habilitar la pantalla (`hardware.display.enabled`) y ver sus logs.

## Decisions

**Tomadas:**

- **GC9A01 redonda 240x240 por SPI en lugar de la OLED SSD1306 I²C.** Es el hardware que hay. Los documentos se actualizan para no dejar dos planes de pantalla.
- **Hilo dentro del hardware agent.** Reutiliza config, logging, unidad y deploy. Un fallo de la pantalla se registra y no tumba los botones.
- **Suscripción propia con `player.subscribe` (SPEC 16).** El protocolo ya admite varios suscriptores. El agente nunca habla con MPD.
- **Copia de ~25 líneas del suscriptor en `hardware-agent`.** `web-agent/ipc.py` vive en otro directorio de deploy; compartirlo obligaría a montar un paquete común.
- **Pillow + `spidev` con un driver propio y mínimo.** Ambos son paquetes `apt`, sin venv ni PyPI (igual que SPEC 05).
- **DC y RST con `gpiozero.DigitalOutputDevice`.** Misma librería y fábrica `lgpio` que los botones; se prueba con `MockFactory`.
- **Cuadro completo en cada redibujo.** 115 KB a 40 MHz son unos 25 ms. Con 1 redibujo por segundo como máximo, no hace falta redibujo parcial.
- **Rotación con Pillow, no con `MADCTL`.** Una sola ruta de código que sirve para cualquier ángulo.
- **Avance local de la posición, 1 tick por segundo en `playing`.** Igual que la página web. Cada push lo corrige.
- **Redibujo solo si cambia la `View`.** Evita tráfico SPI inútil en pausa o detenido.
- **Truncar con "…".** El marquee obligaría a redibujar constantemente.
- **DejaVu Sans (`fonts-dejavu-core`).** La fuente por defecto de Pillow es demasiado chica para 240 px.
- **`hardware.display` opcional y deshabilitada por defecto.** Una Pi sin pantalla se comporta igual que hoy. `install.sh` no necesita agregar la sección a un `player.json` existente.
- **`spiHz` y `rotation` configurables.** Los módulos baratos varían en el reloj que toleran y en la orientación; es calibración física, no una constante.
- **Fallo de init: un `error` y sin reintento.** Reiniciar la unidad lo resuelve; un reintento en bucle solo llenaría el log.
- **`install.sh` verifica, no instala ni activa SPI.** Mismo criterio que SPEC 05. Falta `/dev/spidev0.0` → warning, no error, porque la pantalla puede estar deshabilitada.
- **Pillow fijado en 11.1.0 para desarrollo.** Es la versión de `python3-pil` medida en la Pi (Pi OS trixie, `11.1.0-5+deb13u4`). El plan asumía Bookworm (9.4.0); corregido al implementar. `rgb565()` usa `ImageMath.lambda_eval` en Pillow ≥ 11 (`eval` quedó obsoleto) y `eval` en versiones anteriores.

**Descartadas:**

- **Proceso y unidad aparte (`display-agent`).** Aísla mejor, pero suma una unidad, pasos de instalación y una config.
- **Framebuffer del kernel (`panel-mipi-dbi`).** Requiere un blob de firmware de init y tocar `config.txt`.
- **`luma.lcd`.** Solo está en PyPI y rompe la decisión de no usar venv.
- **Carátula y menú.** Cada uno en su propia spec.
- **Redibujar solo con cada push.** El anillo quedaría quieto durante toda la canción.
- **Apagar la pantalla por inactividad.** No hay pin BL. `DISPOFF` queda para una spec futura (batería).
- **Que `install.sh` active SPI y reinicie.** Tocar `config.txt` y reiniciar es decisión del administrador.

## Risks

| Riesgo | Mitigación |
|---|---|
| Conectar VCC a 5 V o cablear mal SPI daña el módulo o la Pi. | Tabla de cableado en `gpio-map.md`. VCC solo a 3.3 V (pin 17). Verificar el pinout serigrafiado del módulo antes de energizar. Cablear con la Pi apagada. |
| La secuencia de init del GC9A01 varía entre módulos (colores invertidos, imagen espejada). | `rotation` configurable. La secuencia se toma de la hoja de datos o de un driver de referencia conocido y se valida en la Pi con el criterio "rojo se ve rojo". Si hace falta `INVON`/`MADCTL` distinto, se ajusta y se documenta. |
| 40 MHz es inestable con cables dupont largos (basura en pantalla). | `spiHz` configurable. Se baja (p. ej. 20 MHz) y el valor final queda documentado. |
| Un dibujo con Pillow en la Pi Zero 2 W tarda más de 1 s y el tick se atrasa. | Render simple (texto y un arco). Se mide en la Pi; el tick usa el reloj monotónico, no acumula sleeps. ponytail: sin caché de capas; agregar si el render pasa de ~200 ms. |
| Un cuadro a medio enviar mientras se detiene el agente. | `stop()` espera a que termine el `show()` en curso antes de cerrar SPI y GPIO. |
| `spidev` o `/dev/spidev0.0` no está, o el usuario no está en el grupo `spi`. | Import y apertura adentro del `try`: un `error` claro en el log y los botones siguen. `install.sh` avisa si falta el device; la unidad agrega `spi`. |
| GPIO5/GPIO6 en uso por otro HAT futuro. | Configurables en `player.json`. La validación rechaza choques con los botones. |
| Diferencias entre Pillow de pip (Windows) y de apt (Pi). | `Pillow==11.1.0` fijado en `requirements-dev.txt`. Solo se usa API estable (`ImageDraw.text`, `arc`, `ImageFont.truetype`). |
| La fuente DejaVu tiene otra ruta en otra versión de Pi OS. | Ruta fija `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`. Si no está, `error` al iniciar la pantalla, sin tumbar los botones. |

## What is **not** in this spec

- Carátula del álbum.
- Menú con el botón `menu`.
- Marquee.
- Apagar o dormir la pantalla.
- Redibujo parcial, DMA o framebuffer del kernel.
- Pantalla de arranque.
- Brillo o temas.
- Cambios en el Service C# o en el contrato IPC.
- Activar SPI o instalar paquetes desde `install.sh`.

Cada uno, si llega, va en su propia spec.
