# SPEC 08 — Web agent: control remoto que imita los botones

> **Status:** Implemented
> **Depends on:** SPEC 03, SPEC 04, SPEC 05
> **Date:** 2026-10-20
> **Objective:** Agregar un web agent en Python (solo stdlib) que sirve una página con los 6 botones y el estado actual, y los traduce a `button.pressed` / `player.get_snapshot` por el socket IPC, accesible solo desde la red local e instalado como unidad systemd con el mismo deploy.

## Scope

**In:**

- `src/web-agent/` (Python 3, solo stdlib):
  - `config.py`: lee `ipc.unixSocketPath` y `web.port` de `player.json`; `ConfigError` nombrando el campo.
  - `ipc.py`: una conexión por pedido al socket; `press(name)` envía `button.pressed` (sin `sequence`); `snapshot()` envía `player.get_snapshot` y devuelve la línea de respuesta.
  - `server.py`: `ThreadingHTTPServer` en `::` (dual stack) con las rutas `GET /`, `POST /api/buttons/<name>`, `GET /api/snapshot`; filtro de cliente por rangos privados + `::1` + `fe80::/10` (403 si no).
  - `main.py`: arranque, logs a stderr como el hardware agent (`ready: http://[::]:8080`), SIGTERM/SIGINT.
  - `index.html`: 6 botones grandes con íconos y etiquetas en español, línea de estado (estado, pista, volumen) con `GET /api/snapshot` cada 2 s; CSS y JS inline; usable en móvil.
- `player.json` / `config/player.example.json`: sección `web: { "port": 8080 }`.
- Service: el log de `button.pressed` omite `(sequence …)` cuando no viene.
- `deploy/openplayer-web.service`, `install.sh` y `deploy.ps1` (mismo tgz; espera `ready:`). `install.sh` agrega `"web": {"port": 8080}` a un `player.json` existente que no lo tenga.
- Pruebas `tests/web-agent/` (pytest, servidor TCP falso + HTTP real en puerto aleatorio).
- Docs: `architecture.md` (web agent y contrato HTTP), README, `assembly.md`.

**Out of scope (for future specs):**

- Autenticación (contraseña o token).
- HTTPS.
- Explorar la biblioteca, elegir pistas, barra de progreso, seek.
- Actualización en vivo (SSE/WebSocket).
- Acceso fuera de la red local.
- Cambios de comportamiento en el Service o el Core (solo el log).

## Data model

**`player.json`** (nueva sección):

```json
"web": {
  "port": 8080
}
```

Validación: `port` entero 1024–65535 (no bool). Puerto < 1024 requeriría privilegios.

**`src/web-agent/config.py`:**

```python
@dataclass(frozen=True)
class WebConfig:
    socket_path: str   # ipc.unixSocketPath, no vacío
    port: int          # web.port
```

**Contrato HTTP:**

| Método y ruta | Éxito | Errores |
|---|---|---|
| `GET /` | `200` `text/html` (`index.html`) | — |
| `POST /api/buttons/<name>` (`play_pause`, `previous`, `next`, `volume_up`, `volume_down`, `menu`) | `204` sin cuerpo | `404` nombre desconocido; `503` socket inalcanzable |
| `GET /api/snapshot` | `200` `application/json`: la línea `player.snapshot` tal cual | `502` si el Service responde `error`; `503` socket inalcanzable o sin respuesta en 2 s |
| Cualquier otra ruta o método | — | `404` (`405` si la ruta existe con otro método) |
| Cliente fuera de rangos permitidos | — | `403` en todas las rutas |

Rangos permitidos: `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `::1`, `fe80::/10` (IPv4 mapeadas `::ffff:a.b.c.d` se evalúan como IPv4).

**Mensajes IPC** (sin cambios, `architecture.md` §7): `{"type":"button.pressed","button":"<name>"}` y `{"type":"player.get_snapshot"}`.

## Implementation plan

1. `src/web-agent/config.py` + `web` en `config/player.example.json` + pruebas de configuración (válida, puerto fuera de rango/bool, campo faltante, socket vacío).
2. `ipc.py`: `press()` y `snapshot()` con una conexión por pedido y `connect` inyectable; pruebas con el servidor TCP falso (línea exacta enviada, respuesta devuelta, `error`, servidor caído, timeout de 2 s).
3. `server.py` + `index.html`: rutas, filtro de cliente y códigos del contrato; pruebas HTTP reales en puerto aleatorio con `ipc` falso (cada código de la tabla, incluido 403 con un cliente no permitido simulado).
4. `main.py`: arranque, `ready:`, señales, exit 1 con config inválida. Service: log de `button.pressed` sin `(sequence …)` cuando falta, con su prueba.
5. Deploy: `deploy/openplayer-web.service`, `install.sh` (instala, habilita, espera `ready:`, agrega `web` a un `player.json` existente sin esa sección), `deploy.ps1` y tgz con `web-agent/`; `systemd-analyze verify`.
6. Docs: `architecture.md` (web agent y contrato HTTP), README (uso y logs), `assembly.md` (instalación y URL).
7. Verificación en la Pi: desde Windows y desde un móvil en la misma red, cada botón actúa sobre MPD, el estado se actualiza, Service detenido → 503 y la página lo muestra, reboot → todo arriba.

## Acceptance criteria

**Windows (automatizable):**

- [x] `pytest tests/web-agent` y `pytest tests/hardware-agent` pasan.
- [x] `config.py` rechaza con `ConfigError`, nombrando el campo: `web.port` faltante, no entero, bool o fuera de 1024–65535, y `ipc.unixSocketPath` vacío.
- [x] `press("next")` envía exactamente `{"type":"button.pressed","button":"next"}\n` y cierra la conexión.
- [x] `snapshot()` devuelve la línea de respuesta; con el servidor caído o sin respuesta en 2 s lanza un error que el servidor convierte en `503`.
- [x] Cada fila del contrato HTTP devuelve el código indicado (204, 404, 405, 502, 503, 200 con `text/html` y `application/json`).
- [x] Un cliente fuera de los rangos permitidos recibe `403`; `::ffff:192.168.x.x` se trata como permitido.
- [x] `main.py` con config inválida sale con exit 1 y un mensaje que nombra el campo.
- [x] El web agent solo importa stdlib (verificable con grep).
- [x] El Service registra `Button Next` (sin `sequence`) cuando el mensaje no la trae; `dotnet test` pasa.

**Raspberry Pi:**

- [x] `deploy.ps1` termina con exit 0 y `openplayer`, `openplayer-hardware` y `openplayer-web` quedan `active`; el web agent corre como `openplayer`.
- [x] `http://mpi3-player.local:8080` abre desde el navegador de Windows y desde un móvil en la misma red.
- [x] Cada uno de los 6 botones produce una línea `Button …` en el log del Service; play/pause, next, previous y volumen cambian `mpc status` como los botones físicos.
- [x] La línea de estado refleja estado, pista y volumen en 2 s o menos tras un cambio hecho con `mpc`.
- [x] Con el Service detenido, un botón devuelve `503` y la página muestra "Sin conexión con el reproductor"; al reiniciarlo, vuelve a funcionar sin recargar.
- [x] Tras `sudo reboot`, la página funciona sin intervención.

**Documentación:**

- [x] `architecture.md` describe el web agent y el contrato HTTP.
- [x] README explica la URL, `systemctl`/`journalctl` de `openplayer-web` y cómo correr las pruebas.
- [x] `assembly.md` menciona la instalación con el deploy y el puerto 8080.

## Decisions

**Tomadas:**

- **Proceso Python aparte (web agent), no ASP.NET en el Service.** Sigue el patrón del hardware agent: las entradas emiten eventos por el socket y el Service decide. Sin cambiar de SDK, sin compartir el lock fuera de `IpcServer`, ~10 MB de RAM en vez de ~20+ MB y publish más grande.
- **Solo stdlib (`http.server`, `ThreadingHTTPServer`).** Seis botones y un JSON no justifican Flask/FastAPI ni dependencias nuevas en la Pi.
- **Sin autenticación; filtro por rangos privados.** Solo controla reproducción (no escribe archivos como Samba). Igual que el resto: nunca expuesto a Internet.
- **Dual stack en `::` con `fe80::/10` y `::1`.** Windows resuelve `.local` primero a IPv6 link-local (lección de SPEC 07).
- **Una conexión al socket por pedido HTTP.** Sin estado ni reconexión; el Service ya acepta varios clientes y serializa con su lock.
- **Sin `sequence`.** Es opcional en el contrato; el Service solo ajusta su log.
- **Polling de `/api/snapshot` cada 2 s.** Suficiente para una línea de estado; SSE/WebSocket quedan para otra spec.
- **Config propia mínima en `web-agent/`.** Duplica la lectura de `ipc.unixSocketPath`, pero una sección `hardware` inválida no tumba la web.
- **`index.html` único, vanilla, en español.** Sin build ni framework; se sirve desde el mismo proceso.
- **Unidad systemd propia (`openplayer-web`).** Se habilita/deshabilita sin tocar el Service ni el hardware agent.
- **`install.sh` agrega `web` si falta en `player.json`.** `install.sh` nunca sobrescribe `player.json`; sin la sección, el primer deploy fallaría con `web.port is missing`. Solo se agrega la sección faltante con el valor del ejemplo (hallado al implementar).

**Descartadas:**

- **ASP.NET Core en el Service.** Más RAM y tamaño, y mezcla HTTP con el núcleo; ver arriba.
- **HTTP dentro del hardware agent.** Un fallo de GPIO tumbaría también la web.
- **Contraseña/token.** Revisar si se agregan acciones destructivas (borrar música, playlists).
- **Conexión persistente al socket.** Complejidad del `Sender` sin beneficio para pedidos esporádicos.

## Risks

- **Cualquiera en la red local puede controlar el reproductor.** Aceptado: solo reproducción y volumen. Mitigación: rangos privados; autenticación en otra spec si hace falta.
- **Pedidos HTTP concurrentes.** `ThreadingHTTPServer` abre un hilo por pedido y cada uno una conexión al socket; el Service los serializa con su lock. Sin límite de hilos: aceptable en LAN; un cliente abusivo podría crear muchos hilos.
- **Polling con la página abierta.** Un `player.get_snapshot` cada 2 s por pestaña; carga mínima, pero varias pestañas multiplican los pedidos a MPD.
- **Puerto 8080 ocupado.** El web agent sale con error, systemd reintenta según `StartLimitBurst` y queda `failed`; `install.sh` lo detecta al no ver `ready:`. Cambiar `web.port`.
- **Volumen desincronizado del estado.** Entre dos sondeos la línea de estado puede mostrar un valor viejo hasta 2 s.
- **Filtro por IP con proxies/NAT.** Se evalúa la IP de origen de la conexión TCP; detrás de un proxy inverso (no previsto) todos los clientes parecerían locales.
