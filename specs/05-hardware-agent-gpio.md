# SPEC 05 — Agente Python de hardware: botones GPIO

> **Status:** Approved
> **Depends on:** SPEC 04
> **Date:** 2026-10-20
> **Objective:** Implementar el hardware agent en Python que lee los 6 botones GPIO con `gpiozero` y envía `button.pressed` por el socket IPC, instalado como unidad systemd con el mismo deploy y verificable en la Pi con un cable de puente a GND.

## Scope

**In:**

- `src/hardware-agent/`, en Python 3 y solo con stdlib más `gpiozero`:
  - `config.py`: lee `player.json` (secciones `hardware.buttons`, `hardware.debounceSeconds` e `ipc.unixSocketPath`) y lo valida.
    - Los 6 nombres IPC, cada uno con un pin entero entre 0 y 27, sin repetirse.
    - `debounceSeconds` entre 0.01 y 1; ruta del socket no vacía.
    - Si algo es inválido, exit 1 con un mensaje que nombra el campo.
  - `buttons.py`: un `gpiozero.Button` por pin, con pull-up interno y `bounce_time` igual al debounce. El callback `when_pressed` solo encola el nombre del botón.
  - `sender.py`: hilo que toma eventos de la cola y los envía por el socket Unix como `{"type":"button.pressed","button":…,"sequence":N}\n`.
    - `sequence` empieza en 1 y es por proceso.
    - Reconexión con espera incremental de 0.5 s a 10 s. Solo se registran los cambios de estado (`connected` / `disconnected`).
    - Detecta que el Service cerró la conexión aunque no haya pulsaciones (sondeo en reposo).
    - Una pulsación sin conexión se descarta con un warning; nunca se encola para después.
    - La conexión es inyectable (`connect`), para poder probarla en Windows.
  - `main.py`: carga la config, arma los botones y el sender, registra con `logging` en stderr y termina limpio con SIGTERM o Ctrl+C (exit 0).
  - `requirements-dev.txt`: `gpiozero` y `pytest`, solo para desarrollo y pruebas.
- `tests/hardware-agent/` (pytest, corre en Windows con `MockFactory` de `gpiozero`):
  - `test_config.py`: config válida y cada caso inválido.
  - `test_sender.py`: contra un servidor falso TCP local (conexión inyectable). Cubre el formato y `sequence`, descarte sin conexión, reconexión tras el cierre del servidor y detección del cierre en reposo.
  - `test_buttons.py`: activar un pin simulado encola el nombre correcto, y un rebote dentro del debounce no duplica el evento.
- `deploy/openplayer-hardware.service`:
  - `ExecStart=/usr/bin/python3 /opt/openplayer/hardware-agent/main.py`;
  - `StartLimitIntervalSec=60` y `StartLimitBurst=5`;
  - `Environment=GPIOZERO_PIN_FACTORY=lgpio` y `LG_WD=/tmp`, con `PrivateTmp=true`;
  - mantiene `User=openplayer`, `SupplementaryGroups=gpio`, `Wants`/`After=openplayer.service` y el hardening.
- `deploy/install.sh`:
  - verifica que estén `python3-gpiozero` y `python3-lgpio`; si faltan, sale con un mensaje claro;
  - copia el agente a `/opt/openplayer/hardware-agent`;
  - instala la unidad del agente, la habilita, la reinicia y comprueba que queda `active`.
- `deploy.ps1`: incluye el agente y su unidad en lo que copia a la Pi.
- Documentación:
  - `gpio-map.md`: el procedimiento seguro con el cable de puente y el ajuste de debounce.
  - `architecture.md`: §5 (hardware-agent) y §13 (fases).
  - README: cómo probar y ver los logs del agente.
  - `assembly.md` §8.

**Out of scope (para futuras specs):**

- OLED y consulta de `player.get_snapshot` desde el agente.
- Pulsación larga, doble clic y combinaciones.
- Encolar pulsaciones para enviarlas al reconectar.
- Deduplicación por `sequence` en el Service.
- Cableado físico definitivo de los botones.
- Instalar dependencias con `apt` desde `install.sh` (solo verifica).
- Un venv o paquetes desde PyPI en la Pi.
- Cambios en el Service C# o en el contrato IPC.

## Data model

Archivos:

```text
src/hardware-agent/
  main.py                 // entrada
  config.py               // AgentConfig + load_config()
  buttons.py              // create_buttons()
  sender.py               // Sender (hilo)
  requirements-dev.txt    // gpiozero==2.0.1, pytest
tests/hardware-agent/
  conftest.py             // añade src/hardware-agent al sys.path; MockFactory
  test_config.py
  test_sender.py
  test_buttons.py
deploy/
  openplayer-hardware.service   // modificado
  install.sh                    // + agente
deploy.ps1                      // + agente
```

En la Pi:

```text
/opt/openplayer/hardware-agent/*.py      root:root 0644
/etc/systemd/system/openplayer-hardware.service
```

Python:

```python
BUTTON_NAMES = ("play_pause", "previous", "next", "volume_up", "volume_down", "menu")

@dataclass(frozen=True)
class AgentConfig:
    socket_path: str
    pins: dict[str, int]          # nombre IPC → BCM
    debounce_seconds: float

class ConfigError(Exception): ...  # mensaje nombra el campo

def load_config(path: str) -> AgentConfig: ...

def create_buttons(config: AgentConfig, on_press: Callable[[str], None]) -> list[Button]: ...
    # Button(pin, pull_up=True, bounce_time=config.debounce_seconds)
    # when_pressed → on_press(name)

class Sender:
    def __init__(self, socket_path: str, *, connect: Callable[[], socket.socket] | None = None,
                 min_backoff=0.5, max_backoff=10.0): ...
        # connect por defecto: AF_UNIX a socket_path; en pruebas, TCP a 127.0.0.1
    def press(self, name: str) -> None: ...   # thread-safe: encola; nunca bloquea
    def start(self) -> None: ...              # arranca hilo daemon
    def stop(self) -> None: ...               # termina el hilo y cierra el socket
```

`main.py`:

```text
python3 main.py [ruta/player.json]   # por defecto ../player.json relativo a main.py
exit 0: SIGTERM o Ctrl+C
exit 1: config inválida o falta gpiozero
```

Mensaje enviado (contrato SPEC 03, sin cambios):

```json
{"type":"button.pressed","button":"next","sequence":1}
```

Ciclo del `Sender`:

| Estado | Comportamiento |
|---|---|
| Desconectado | Intenta conectar. Si falla, espera el backoff (0.5 → 1 → 2 … → 10 s); durante la espera descarta los eventos que llegan, con un warning cada uno. |
| Conectado | Toma un evento con `queue.get(timeout=1)` y lo envía. Si la cola está vacía, sondea el socket con `select`: si es legible y `recv` devuelve `b""`, pasa a desconectado. |
| Error al enviar | El evento se pierde con un warning y pasa a desconectado. |
| Transición | Registra un log `info` solo al conectar y un `warning` solo al desconectar. El backoff vuelve a 0.5 s al conectar. |

Logs (formato `nivel: mensaje` en stderr, lo captura journald):

```text
info: connected to /run/openplayer/hardware.sock
info: button next (sequence 3)
warning: disconnected from /run/openplayer/hardware.sock
warning: dropped next: not connected
```

## Implementation plan

1. Crear `src/hardware-agent/config.py` y `requirements-dev.txt`, con `tests/hardware-agent/conftest.py` y `test_config.py`.
   - Cubrir: `player.example.json` válido; nombre de botón faltante o extra; pin fuera de rango, no entero o repetido; debounce fuera de rango; ruta del socket vacía; archivo inexistente; JSON inválido.
   - Verificar: `pytest tests/hardware-agent` en verde en Windows (venv local con `requirements-dev.txt`).
2. Crear `sender.py` (con `connect` inyectable) y `test_sender.py` contra un servidor TCP local falso. Cubrir:
   - formato exacto de la línea y `sequence` incremental;
   - sin servidor, `press()` no bloquea y el evento se descarta;
   - el servidor cierra estando en reposo → se detecta desconexión y reconecta al volver;
   - error al enviar → descarte y reconexión;
   - el backoff no pasa de `max_backoff`;
   - `stop()` termina el hilo.
3. Crear `buttons.py` y `test_buttons.py` con `MockFactory`.
   - Activar el pin de `next` → `on_press("next")`.
   - Dos activaciones dentro del debounce → un solo evento.
   - Los 6 pines del ejemplo crean 6 botones con pull-up.
4. Crear `main.py`: argumento opcional con la ruta, logging, arma todo y espera la señal; SIGTERM o Ctrl+C → `stop()` → exit 0; `ConfigError` → exit 1.
   - Verificar en Windows con `GPIOZERO_PIN_FACTORY=mock`: arranca, registra los intentos de conexión sin hacer spam y Ctrl+C sale con 0. Con config inválida → exit 1 y un mensaje que nombra el campo.
5. Actualizar `deploy/openplayer-hardware.service`, `deploy/install.sh` (verificación de paquetes, copia a `/opt/openplayer/hardware-agent`, unidad, `enable`, `restart`, comprobación de `active`) y `deploy.ps1` (copiar el agente y su unidad).
   - Verificar desde Windows: `deploy.ps1` → exit 0 y las dos unidades `active`; `journalctl -u openplayer-hardware` muestra `connected`.
6. Actualizar la documentación:
   - `gpio-map.md`: prueba con el cable de puente y ajuste de debounce;
   - `architecture.md` §5 y §13;
   - README: logs, prueba con el cable y pruebas Python;
   - `assembly.md` §8.
7. Verificar en la Pi con el cable de puente (criterios manuales).

## Acceptance criteria

**Windows (automatizable):**

- [ ] `pytest tests/hardware-agent` pasa todas las pruebas.
- [ ] `config.py` rechaza con `ConfigError`, nombrando el campo: botón faltante o extra, pin fuera de 0–27, no entero o repetido, `debounceSeconds` fuera de 0.01–1 y `unixSocketPath` vacío.
- [ ] El `Sender` envía exactamente `{"type":"button.pressed","button":…,"sequence":N}\n`, con `sequence` incremental desde 1.
- [ ] Sin servidor, `press()` vuelve de inmediato y el evento se descarta (nunca se envía más tarde).
- [ ] Si el servidor cierra la conexión en reposo, el `Sender` lo detecta en 2 s o menos y reconecta cuando el servidor vuelve.
- [ ] El backoff de reconexión no supera `max_backoff` y vuelve al mínimo tras conectar.
- [ ] Con `MockFactory`, activar el pin de cada botón produce `on_press` con su nombre, y dos activaciones dentro del debounce producen un solo evento.
- [ ] `main.py` con config inválida sale con exit 1 y un mensaje que nombra el campo.
- [ ] El agente solo importa stdlib y `gpiozero` (verificable con grep).
- [ ] `dotnet build` y `dotnet test` siguen pasando.

**Raspberry Pi (manual; cable dupont solo entre GPIO y GND):**

- [ ] `deploy.ps1` termina con exit 0, y `openplayer` y `openplayer-hardware` quedan `active`.
- [ ] `ps -o user= -C python3` muestra `openplayer` para el agente, y `journalctl -u openplayer-hardware` muestra `connected to /run/openplayer/hardware.sock`.
- [ ] Puentear GPIO17 (pin 11) a GND (pin 9) alterna play/pause según `mpc status`.
- [ ] Puentear GPIO22 (pin 15) a GND (pin 14) hace `next` según `mpc status`.
- [ ] Puentear GPIO23 o GPIO24 cambia el volumen en 5 según `mpc volume`.
- [ ] 10 toques sobre un mismo pin producen 10 líneas `button` en el log del agente y 10 en el del Service. Si hay eventos dobles, se ajusta `hardware.debounceSeconds` y el valor final queda documentado.
- [ ] `sudo systemctl restart openplayer`: el agente registra `disconnected` y luego `connected` en 10 s o menos, y el siguiente toque funciona.
- [ ] Con el Service detenido (`sudo systemctl stop openplayer`), un toque produce `dropped …: not connected` y el agente sigue `active`.
- [ ] Después de `sudo reboot`, las dos unidades están `active` y un toque funciona sin intervención.

**Documentación:**

- [ ] `gpio-map.md` describe la prueba con el cable de puente (solo GPIO↔GND, nunca 3.3 V ni 5 V) y el ajuste de debounce.
- [ ] `architecture.md` §5 describe el agente implementado y §13 marca la fase.
- [ ] El README explica cómo ver los logs del agente, cómo probar con el cable y cómo correr las pruebas Python.
- [ ] `assembly.md` §8 describe la instalación del agente con el deploy.

## Decisions

- **Sí:** paquetes del sistema (`python3-gpiozero`, `python3-lgpio`) y `/usr/bin/python3`, sin venv. Ya están instalados en Pi OS; compilar `lgpio` con pip en la Pi Zero es lento y frágil.
- **No:** venv con pip. Añade un paso de build en la Pi sin ganancia mientras el agente use solo stdlib y `gpiozero`.
- **Sí:** `gpiozero` con `lgpio` (forzado con `GPIOZERO_PIN_FACTORY`). Es la librería recomendada en Pi OS reciente, trae debounce y pull-up, y su `MockFactory` permite probar en Windows.
- **No:** `RPi.GPIO`. No funciona en kernels recientes sin compatibilidad.
- **Sí:** leer el mismo `player.json` (`hardware.*` e `ipc.unixSocketPath`). Una sola fuente de configuración, que el deploy ya conserva.
- **Sí:** descartar las pulsaciones sin conexión. Reenviar un `next` segundos después sorprende más que perder una pulsación durante un reinicio del Service.
- **Sí:** el callback de GPIO solo encola, y un hilo aparte maneja el socket. La lectura de botones nunca se bloquea esperando al Service (`gpio-map.md` §4).
- **Sí:** detectar el cierre en reposo con `select` y `recv`. Sin esto, la primera pulsación después de reiniciar el Service se perdería sin aviso.
- **Sí:** solo registrar cambios de estado de la conexión, no cada intento (`architecture.md` §7).
- **Sí:** `sequence` por proceso, desde 1. Permite detectar duplicados en los logs sin persistir estado.
- **Sí:** `connect` inyectable en `Sender`, probado con TCP local en Windows. Python en Windows no tiene `AF_UNIX`; el stream TCP tiene la misma semántica, y el `AF_UNIX` real se verifica en la Pi.
- **No:** saltar las pruebas del sender en Windows o usar WSL. Dejaría la lógica de reconexión sin pruebas en el entorno de desarrollo, o añadiría una dependencia.
- **Sí:** incluir `menu` (GPIO25). El contrato ya lo define; el Service lo ignora.
- **Sí:** `PrivateTmp=true` y `LG_WD=/tmp`. `lgpio` crea archivos de notificación en el directorio de trabajo, y `ProtectSystem=strict` deja `/opt` de solo lectura.
- **Sí:** el mismo `install.sh` y `deploy.ps1` instalan el agente. Un comando despliega todo.
- **Sí:** `install.sh` verifica los paquetes Python pero no los instala. Instalar paquetes del sistema es una decisión del administrador; un mensaje claro basta.
- **Sí:** validar con un cable dupont entre GPIO y GND. Es exactamente el circuito del botón con pull-up interno; el software no cambia al cablear botones reales.
- **Sí:** el debounce se calibra en `player.json`. El rebote real depende del botón o del cable; es un ajuste físico, no una constante de código.

## Risks

| Riesgo | Mitigación |
|---|---|
| Tocar 3.3 V o 5 V con el cable de puente en lugar de GND daña el GPIO o la Pi. | Procedimiento documentado: identificar GND (pin 9 o 14) con el pinout oficial antes de tocar. Conectar primero el extremo en GND y luego tocar el GPIO; nunca otros pines. |
| El cable de puente rebota mucho más que un botón y genera eventos dobles. | `debounceSeconds` calibrable en `player.json`. El criterio acepta subir el valor y documentarlo; con botones reales se recalibra. |
| `lgpio` falla bajo el hardening de systemd (`ProtectSystem=strict`, `/dev/gpiochip0`). | `PrivateTmp` y `LG_WD=/tmp`, y `SupplementaryGroups=gpio` para el device. Si falla, el `journalctl` del criterio lo muestra; se ajusta la unidad y se documenta. |
| `MockFactory` no reproduce exactamente el debounce real de `lgpio`. | Las pruebas cubren la lógica (pin→nombre, un evento por activación); el rebote real se valida en la Pi. |
| Un test de reconexión depende del timing (sondeo de 1 s). | Timeouts generosos (≤ 5 s) con espera activa de la condición, sin sleeps fijos. |
| `gpiozero` cambia su API entre la versión de pip (Windows) y la de apt (Pi, 2.0.1). | Fijar `gpiozero==2.0.1` en `requirements-dev.txt` para igualar la Pi. |
| Al detener `openplayer`, systemd también detiene el agente por la dependencia. | `Wants=` no propaga la parada (solo `Requires=` o `BindsTo=`); se verifica en la Pi con el criterio de "Service detenido". |

## What is **not** in this spec

- OLED y `player.get_snapshot` desde el agente.
- Pulsación larga, doble clic y combinaciones.
- Encolar pulsaciones para reenviar.
- Deduplicación por `sequence`.
- Cableado físico definitivo.
- `apt install` desde `install.sh`.
- venv o PyPI en la Pi.
- Cambios en el Service C# o en el contrato IPC.

Cada uno de estos, si llega, va en su propia spec.
