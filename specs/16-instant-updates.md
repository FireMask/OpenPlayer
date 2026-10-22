# SPEC 16 — Actualización instantánea

> **Status:** Implemented
> **Depends on:** SPEC 03, SPEC 08, SPEC 11, SPEC 15
> **Date:** 2026-10-22
> **Objective:** Que el Service empuje un `player.snapshot` a los suscriptores IPC (`player.subscribe`) cada vez que MPD avisa un cambio (`idle player mixer playlist options`), y que el web agent lo reenvíe por SSE (`GET /api/events`) para que la página se actualice al instante sin sondear cada 2 s.

## Scope

**In:**

- Core:
  - Mensaje IPC `player.subscribe` (sin campos, sin `request`): la conexión queda dedicada a la suscripción.
- Mpd:
  - `MpdClient.IdleAsync` / `IPlayer.WaitForChangeAsync`: `idle player mixer playlist options` (antes solo `player`).
- Service (`IpcServer`):
  - `player.subscribe` → responde enseguida con el snapshot actual (`player.snapshot`) y registra al suscriptor; no se leen más pedidos de esa conexión.
  - El observador (SPEC 15), tras cada `WaitForChangeAsync`, envía el mismo snapshot que usa para el historial a todos los suscriptores.
  - Varios suscriptores; uno cuya escritura falla o tarda más de 2 s se descarta (warning, se cierra la conexión).
  - MPD caído en el observador: los suscriptores reciben la línea de error (`{"type":"error","request":"player.get_snapshot",...}`) una vez por fallo.
- Web agent:
  - `ipc.py`: `subscribe()` abre la conexión, envía `player.subscribe` y devuelve las líneas a medida que llegan.
  - `server.py`: un hilo de fondo mantiene la suscripción mientras corre el web agent, guarda la última línea y la reparte a las páginas abiertas; si el Service se cae, reparte la línea de error de hoy y reintenta cada 2 s.
  - `GET /api/events` (`text/event-stream`): primero la última línea conocida, luego `data: <línea>` por cambio y `: ping` cada 15 s. Máximo 8 páginas; la 9.ª recibe 503.
- Página (`index.html`):
  - `EventSource("/api/events")`: cada mensaje se procesa igual que la respuesta de `/api/snapshot` hoy (estado, progreso, `queueVersion` → recarga de la cola).
  - Mientras el stream está conectado, sin sondeo; al caer (`onerror`), vuelve el sondeo de 2 s hasta que el navegador reconecte.
- Pruebas: Service (suscripción, push por cambio, error de MPD, suscriptor muerto), Mpd (comando `idle` exacto), web agent (SSE, reparto, tope 8, ping, Service caído).
- Docs: `architecture.md` §5, §7, §9; README.

**Out of scope (for future specs):**

- `stored_playlist`: que la pestaña Listas se actualice sola.
- Suscripción del hardware agent u OLED (el protocolo ya admite varios suscriptores).
- Pruebas con navegador headless.
- Reemplazar los POST de los botones por mensajes en el mismo stream (sigue HTTP normal).
- Autenticación o acceso fuera de la red local.
- Spotify-style, arrastrar para reordenar, "Escuchadas recientemente".

## Data model

**IPC (architecture.md §7):**

| Dirección | Línea | Cuándo |
|---|---|---|
| web agent → Service | `{"type":"player.subscribe"}` | Al abrir la suscripción; único mensaje de esa conexión |
| Service → web agent | `{"type":"player.snapshot",...}` (mismo formato que `player.get_snapshot`) | Enseguida y tras cada cambio |
| Service → web agent | `{"type":"error","request":"player.get_snapshot","message":"..."}` | Cada vez que el observador falla con MPD |

**Core:** `public sealed record SubscribeRequested : IpcMessage;` (sin campos; fuera de `ReplyingTypes` porque responde con snapshots, no con `ok`).

**Mpd:** `IdleAsync` envía `idle player mixer playlist options`.

**Service (`IpcServer`):**

```csharp
// Conexiones suscriptas (SPEC 16). Protegida con lock(_subscribers), no con _commandLock:
// el envío ocurre fuera del lock global para que un suscriptor lento no frene los comandos.
private readonly List<NetworkStream> _subscribers = [];
private static readonly TimeSpan PushTimeout = TimeSpan.FromSeconds(2);
```

**Web agent (`server.py`):**

```python
MAX_EVENT_CLIENTS = 8
PING_SECONDS = 15
RESUBSCRIBE_SECONDS = 2

class Events:
    """Última línea del Service y una cola por página abierta (queue.Queue(maxsize=16)); cola llena → la página se descarta."""
    latest: str | None
    clients: set[queue.Queue]
```

**HTTP:** `GET /api/events` → `200 text/event-stream`, `Cache-Control: no-store`; cuerpo `data: <línea>\n\n` por snapshot y `: ping\n\n` cada 15 s. Con 8 páginas abiertas → `503`.

**Página:** sin datos nuevos; reutiliza el manejo de `player.snapshot` y del error de hoy.

## Implementation plan

1. **Mpd: más subsistemas en `idle`.**
   - `MpdClient.IdleAsync` envía `idle player mixer playlist options`; actualizar pruebas de `MpdClientTests` y `MpdPlayerTests`.
   - El historial (SPEC 15) no cambia: un cambio sin `SongId` nuevo no agrega nada (ya probado).
2. **Core: `player.subscribe`.**
   - `SubscribeRequested` en `IpcMessage`, parser (`player.subscribe` sin campos extra) y pruebas.
3. **Service: suscriptores.**
   - `player.subscribe` → snapshot inmediato bajo el lock, registra la conexión en `_subscribers`; la conexión sigue abierta, se ignoran sus siguientes líneas y se quita al cerrarse.
   - El observador, tras cada snapshot (o error de MPD), envía la línea a todos los suscriptores fuera de `_commandLock`, con timeout de 2 s; falla o timeout → warning y se quita.
   - Pruebas: snapshot inicial, push tras `ChangeAsync`, dos suscriptores, error de MPD, suscriptor que cierra, los pedidos normales siguen funcionando.
4. **Web agent: IPC y reparto.**
   - `ipc.py`: `subscribe()` (generador de líneas; `IpcUnavailable` si no conecta o se corta).
   - `server.py`: clase `Events` y su hilo de fondo (reintento cada 2 s; al caer, reparte la línea de error).
   - Pruebas con el Service falso por TCP: reparto a varias colas, última línea guardada, Service caído → error y reconexión, cola llena → página descartada.
5. **Web agent: `GET /api/events`.**
   - Cabeceras SSE, última línea primero, `data:` por cambio, `: ping` cada 15 s, tope 8 → 503, otros métodos → 405.
   - Pruebas HTTP: primer evento, evento tras push, ping (con intervalo corto inyectable), 9.ª conexión → 503, página cerrada libera su lugar.
6. **Página.**
   - `EventSource("/api/events")`; `onmessage` → mismo manejo que `refresh()`; `onopen` detiene el sondeo; `onerror` lo reanuda (2 s).
7. **Docs.**
   - `architecture.md` §5 (`/api/events`, sondeo solo de respaldo), §7 (`player.subscribe`, push, subsistemas de `idle`), §9 (hecho; pendiente `stored_playlist`).
   - README: la página se actualiza al instante; vuelve a sondear si se corta.

## Acceptance criteria

**Código y pruebas:**

- [x] `IdleAsync` envía exactamente `idle player mixer playlist options`.
- [x] `player.subscribe` se parsea; con tipo erróneo se comporta como cualquier mensaje inválido de hoy. Los campos de más se ignoran, igual que en `player.get_snapshot` (decidido al implementar).
- [x] Tras `player.subscribe`, el Service responde enseguida con un `player.snapshot`.
- [x] Cada cambio del observador envía un `player.snapshot` a todos los suscriptores.
- [x] Un fallo de MPD en el observador envía la línea de error a los suscriptores.
- [x] Un suscriptor que cierra o no lee en 2 s se quita sin afectar a los demás ni a los comandos.
- [x] Otras conexiones siguen respondiendo pedidos normales mientras hay suscriptores.
- [x] El web agent reparte cada línea a todas las páginas abiertas y manda la última al conectar una nueva.
- [x] `GET /api/events` responde `text/event-stream`, manda `: ping` cada 15 s y la 9.ª página recibe 503.
- [x] Con el Service caído, las páginas reciben la línea de error y el web agent reintenta cada 2 s.
- [x] Todas las suites pasan (Core, Mpd, Service, web agent, hardware agent).

**En la Pi:**

- [x] ⏭ en el navegador: título y cola cambian en menos de 0,5 s.
- [x] `mpc next` y `mpc volume 40` desde la Pi: la página lo refleja en menos de 0,5 s.
- [x] Editar la cola en un navegador: el otro navegador la actualiza en menos de 0,5 s.
- [x] Con el stream conectado, la pestaña Red del navegador no muestra `GET /api/snapshot` cada 2 s.
- [x] `sudo systemctl restart openplayer`: la página muestra "Sin conexión con el reproductor" y se recupera sola al volver el Service.
- [x] La barra de progreso sigue avanzando entre eventos.

**Docs:**

- [x] `architecture.md` §5, §7 y §9 describen `/api/events`, `player.subscribe`, los subsistemas de `idle` y el sondeo de respaldo.
- [x] README explica que la página se actualiza al instante.

## Decisions

**Tomadas:**

- **Push por IPC (`player.subscribe`).** El web agent sigue hablando solo con el Service; reutiliza el observador `idle` de SPEC 15.
- **Cada push es el snapshot completo.** La página ya sabe procesarlo; sin pedido extra por cambio.
- **`idle player mixer playlist options`.** Cubre canción, play/pausa, seek, volumen, ediciones de la cola (también desde `mpc` u otro navegador) y `consume`.
- **Conexión dedicada a la suscripción.** No mezcla respuestas con pushes; varios suscriptores para una OLED futura.
- **Envío fuera de `_commandLock`, timeout 2 s.** Un suscriptor lento no frena botones ni pedidos.
- **El web agent se suscribe siempre** (un hilo), no solo con páginas abiertas: menos lógica de arranque/parada.
- **SSE con `EventSource`.** Nativo del navegador, reconecta solo; sin dependencias.
- **Sondeo de 2 s solo de respaldo** cuando el stream cae.
- **Tope de 8 páginas, ping cada 15 s.** Acota hilos del `ThreadingHTTPServer` y detecta páginas muertas.
- **Pruebas sin navegador headless**; la temporización se verifica a mano en la Pi.

**Descartadas:**

- **Web agent hablando con MPD directo.** Rompe la regla de que solo el Service habla con MPD.
- **Aviso sin datos + pedido de snapshot.** Un viaje extra por cambio.
- **Solo `idle player`.** No reflejaría volumen ni ediciones de la cola.
- **Pedidos y pushes en la misma conexión.** Habría que distinguir respuestas de eventos.
- **Suscribirse solo con páginas abiertas.** Ahorra una conexión ociosa a cambio de lógica de ciclo de vida.
- **WebSocket.** Bidireccional innecesario; sin soporte en stdlib.
- **Sondeo lento de seguridad con el stream conectado.** Redundante con la reconexión de `EventSource`.
- **`stored_playlist`.** Spec propia (refresco de la pestaña Listas).

## Risks

| Riesgo | Mitigación |
|---|---|
| Ráfaga de eventos (`playlist.play` = `clear` + `load` + `play`) → varios pushes seguidos | Cada push es liviano; la página ya no recarga la cola mientras otra carga está en curso (`qLoading`) y la siguiente lleva el `queueVersion` final. |
| Más despertares del observador (volumen, cola) | `Observe` solo agrega al historial si cambió `SongId` (SPEC 15); el resto es un snapshot más. |
| Service colgado sin cerrar la conexión: el hilo del web agent espera para siempre | Mismo caso que hoy rompe todo; `systemd` reinicia el Service y la conexión se cierra. ponytail: sin heartbeat IPC; agregar si se ve en la Pi. |
| Móvil en segundo plano corta el stream | `EventSource` reconecta solo al volver; mientras tanto, sondeo de respaldo. |
| 8 páginas ocupan 8 hilos del web agent | Tope fijo; la 9.ª recibe 503 y sigue con sondeo. |
| Página muerta sin cerrar el socket | El `: ping` de 15 s falla al escribir y libera el lugar. |
| La primera línea de una página nueva puede ser vieja (último snapshot) | Llega un push nuevo en el próximo cambio; la barra de progreso avanza localmente igual que hoy. |

## What is **not** in this spec

- `stored_playlist` (refresco automático de Listas).
- Suscripción del hardware agent u OLED.
- Pruebas con navegador headless.
- Botones por el mismo stream; WebSocket.
- Autenticación o acceso fuera de la red local.
- Spotify-style, arrastrar para reordenar, "Escuchadas recientemente".

Cada uno, si llega, va en su propia spec.
