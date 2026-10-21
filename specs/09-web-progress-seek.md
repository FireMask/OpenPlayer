# SPEC 09 — Barra de progreso y seek en la web

> **Status:** Implemented
> **Depends on:** SPEC 03, SPEC 08
> **Date:** 2026-10-21
> **Objective:** Mostrar en la página del web agent una barra de progreso de la pista actual que avanza localmente entre sondeos y permite saltar a una posición, con un nuevo mensaje IPC `player.seek` que el Service ejecuta con `IPlayer.SeekAsync`.

## Scope

**In:**

- Core: `SeekRequested(TimeSpan Position)` en `IpcMessage.cs`; `IpcMessageParser` acepta `{"type":"player.seek","positionSeconds":N}` con `N` entero 0–86400; cualquier otro valor es mensaje inválido (warning, la conexión sigue).
- Service: `IpcServer` ejecuta `SeekAsync` bajo el mismo lock, registra `Seek to N s`, sin respuesta; un `MpdException`/`MpdUnavailableException` solo registra warning.
- Web agent:
  - `ipc.py`: `seek(seconds)`.
  - `server.py`: `POST /api/seek` con cuerpo JSON `{"positionSeconds": N}` (máx. 1 KB) → `204` / `400` / `503`.
  - `index.html`: `<input type="range">` + etiqueta `m:ss / m:ss`; avance local entre sondeos cuando `playing`; arrastre sin saltos por el sondeo; al soltar envía el seek; oculta sin `durationSeconds`, deshabilitada en `stopped`.
- Pruebas: Core (parser), Service (seek llama `SeekAsync`, falla sin tumbar), web agent (ipc + HTTP).
- Docs: `architecture.md` §7 (mensaje) y §5 (contrato HTTP), README.

**Out of scope (for future specs):**

- Actualización instantánea (MPD `idle` → push → SSE) — spec futura.
- Respuesta/ack de `player.seek`.
- Recortar la posición contra la duración en el Service.
- Fracciones de segundo.
- Seek desde botones físicos u OLED.

## Data model

**Mensaje IPC nuevo** (`architecture.md` §7, sin respuesta):

```json
{"type":"player.seek","positionSeconds":83}
```

- `positionSeconds`: entero JSON 0–86400 (24 h, cota para evitar desbordes de `TimeSpan`). Ausente, no entero (`83.5`, `"83"`, `true`), negativo o mayor → inválido: warning en el log y la conexión sigue.

**Core** (`src/OpenPlayer.Core/Messages/IpcMessage.cs`):

```csharp
public sealed record SeekRequested(TimeSpan Position) : IpcMessage;
```

**Service:** `SeekRequested` → `player.SeekAsync(position)` bajo `_commandLock` (MPD `seekcur N`, ya implementado en `MpdPlayer`). Log: `Seek to 83 s`; fallo de MPD (p. ej. detenido o posición fuera de la pista) → warning `Seek failed: …`.

**HTTP** (web agent, se suma al contrato de SPEC 08):

| Método y ruta | Éxito | Errores |
|---|---|---|
| `POST /api/seek` con cuerpo `{"positionSeconds": N}` | `204` | `400` cuerpo ausente, > 1 KB, JSON inválido, o `positionSeconds` no entero / fuera de 0–86400; `503` Service inalcanzable |

**Web agent `ipc.py`:** `Ipc.seek(seconds: int)` → envía `{"type":"player.seek","positionSeconds":seconds}\n` y cierra.

**Página:** sin datos nuevos; usa `positionSeconds`, `durationSeconds` y `state` del snapshot existente.

## Implementation plan

1. Core: `SeekRequested` y parseo de `player.seek` en `IpcMessageParser`, con pruebas (válido, 0, 86400, ausente, `83.5`, `"83"`, `true`, negativo, 86401).
2. Service: `IpcServer` maneja `SeekRequested` (lock, log, warning si MPD falla) con pruebas (`SeekAsync` recibe 83 s; un fallo no cierra la conexión).
3. Web agent: `Ipc.seek()` y `POST /api/seek` con validación del cuerpo, con pruebas (204 y línea exacta enviada; cada caso de 400; 503; 405 con GET).
4. `index.html`: barra `range`, etiqueta `m:ss / m:ss`, avance local, arrastre y seek al soltar, oculta/deshabilitada según el estado.
5. Docs: `architecture.md` §5 y §7, README.
6. Verificación en la Pi: deploy, barra avanzando, seek desde PC y móvil cambia `mpc status`, sin pista / detenido / Service caído.

## Acceptance criteria

**Windows (automatizable):**

- [x] `dotnet test`, `pytest tests/web-agent` y `pytest tests/hardware-agent` pasan.
- [x] `IpcMessageParser` devuelve `SeekRequested(83 s)` para `{"type":"player.seek","positionSeconds":83}`, acepta 0 y 86400, y rechaza (sin lanzar) ausente, `83.5`, `"83"`, `true`, `-1` y `86401`.
- [x] El Service llama `SeekAsync(83 s)` al recibir `player.seek` y no responde nada; si `SeekAsync` lanza `MpdException`, la conexión sigue y el siguiente mensaje se procesa.
- [x] `Ipc.seek(83)` envía exactamente `{"type":"player.seek","positionSeconds":83}\n` y cierra.
- [x] `POST /api/seek` con `{"positionSeconds":83}` → `204` y llega `seek(83)`; cuerpo vacío, > 1 KB, JSON inválido, `"83"`, `83.5`, `-1` o `86401` → `400`; Service caído → `503`; `GET /api/seek` → `405`; cliente fuera de rango → `403`.
- [x] El web agent sigue usando solo stdlib.

**Raspberry Pi (`deploy.ps1` y navegador en PC y móvil):**

- [x] Reproduciendo, la barra y la etiqueta avanzan cada segundo y no saltan atrás al llegar cada sondeo (diferencia ≤ 1 s con `mpc status`).
- [x] Arrastrar la barra y soltar en 2:00 deja `mpc status` en `2:00`–`2:02`, y el log del Service muestra `Seek to 120 s`.
- [x] Mientras se arrastra, el sondeo no mueve la barra.
- [x] En pausa, la barra no avanza y el seek cambia la posición sin reanudar.
- [x] Detenido o sin pista, la barra está deshabilitada u oculta y la etiqueta no muestra tiempos inválidos.
- [x] Con el Service detenido, soltar la barra muestra "Sin conexión con el reproductor".

**Documentación:**

- [x] `architecture.md` §7 describe `player.seek` y §5 suma `POST /api/seek` al contrato.
- [x] README menciona la barra y el seek.

## Decisions

**Tomadas:**

- **Separar en SPEC 09 (barra + seek) y una spec futura (actualización instantánea).** La instantánea exige conexión `idle` persistente a MPD y push por el socket: otro modelo de IPC. Esta spec no toca `OpenPlayer.Mpd`.
- **`player.seek` sin respuesta, como `button.pressed`.** La web ve el resultado en el siguiente sondeo; un ack agregaría un camino de respuesta sin necesidad.
- **Validación en Core: entero 0–86400.** El Service no consulta la duración antes de saltar (evita una consulta extra a MPD); fuera de la pista o detenido, MPD falla y se registra warning, igual que `next` sin reproducir.
- **Segundos enteros.** Coinciden con el snapshot; fracciones no aportan con un dedo en una barra.
- **`POST /api/seek` con cuerpo JSON.** Mismo estilo que el resto de la API; límite de 1 KB para no leer cuerpos arbitrarios.
- **`<input type="range">` nativo.** Táctil y teclado sin código propio; el arrastre se protege del sondeo y el seek se envía solo al soltar.
- **Avance local entre sondeos.** Cuando `playing`, la posición se extrapola en el navegador y cada sondeo la corrige; sin pedidos extra a la Pi.

**Descartadas:**

- **Todo en una spec.** Toca Core, Mpd, Service, web agent y el modelo IPC; demasiado para una iteración.
- **Recortar contra la duración en el Service.** Consulta extra a MPD; la página ya limita la barra a la duración.
- **Barra propia (div + clic).** Más código y peor accesibilidad que `range`.
- **Seek con query string (`?s=83`).** Inconsistente con el cuerpo JSON elegido.

## Risks

- **Seek mientras se cambia de pista.** Si la pista cambia entre el último sondeo y soltar la barra, el seek se aplica a la nueva pista con la posición elegida para la anterior. Ventana ≤ 2 s; aceptado hasta la spec de actualización instantánea.
- **Extrapolación desfasada.** Si el reloj del navegador se suspende (pestaña en segundo plano en el móvil), la barra puede quedar adelantada o atrasada hasta el siguiente sondeo; cada sondeo la corrige.
- **Seek fuera de la pista.** Con una duración vieja en la página, MPD puede rechazar el `seekcur`; solo warning en el log y la barra vuelve a la posición real en el siguiente sondeo.
- **Seeks repetidos.** Soltar varias veces seguidas envía varios `player.seek`; el lock del Service los serializa. Sin límite de frecuencia: aceptable en LAN.
