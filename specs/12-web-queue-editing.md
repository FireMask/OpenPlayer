# SPEC 12 — Editar la cola desde la web

> **Status:** Approved
> **Depends on:** SPEC 03, SPEC 10, SPEC 11
> **Date:** 2026-10-22
> **Objective:** Permitir quitar, reordenar (↑/↓) y limpiar las pistas de la cola de MPD desde el panel "Cola" del web agent, identificando cada pista por su id de MPD.

## Scope

**In:**

- Core:
  - `LibraryEntry` suma `Id` (int?, id de MPD en la cola; `null` fuera de la cola).
  - `IQueue` suma `RemoveAsync(id)`, `MoveAsync(id, to)` y `ClearAsync()`.
  - Mensajes IPC `queue.remove`, `queue.move` y `queue.clear` (responden `ok`), con su parseo.
  - `queue.page` incluye `id` en cada entrada.
- Mpd:
  - `MpdEntryParser` lee `Id` de cada pista.
  - `MpdQueue`: `deleteid ID`, `moveid ID TO`, `clear`.
- Service:
  - `IpcServer` atiende los tres mensajes bajo el mismo lock.
  - `queue.clear` exitoso deja el nombre de la lista cargada en `null`; quitar y mover no lo cambian.
- Web agent:
  - `ipc.py`: `remove_from_queue(id)`, `move_in_queue(id, to)`, `clear_queue()`.
  - `server.py`: `DELETE /api/queue/tracks/{id}`, `POST /api/queue/move` `{"id","to"}`, `DELETE /api/queue`.
  - `index.html`:
    - Cada fila del panel "Cola" suma ↑ / ↓ / ✕ como en una lista abierta de Listas; tocar la fila sigue reproduciéndola.
    - ↑ deshabilitado en la primera fila, ↓ en la última de la cola.
    - Botón "Limpiar" en el encabezado del panel, con `confirm()` nativo; oculto con la cola vacía.
    - Tras cada operación exitosa, la cola se recarga.
- Pruebas: Core (parser, serializador), Mpd (`Id`, comandos exactos, `ACK`), Service (nombre tras `clear`), web agent (ipc + HTTP).
- Docs: `architecture.md` §5, §6, §7; README.

**Out of scope (for future specs):**

- Agregar a la cola desde Biblioteca o Listas sin reemplazarla.
- Guardar la cola como playlist.
- Marcar la lista como "modificada" en el encabezado.
- Arrastrar y soltar para reordenar.
- Deshacer.
- Cambiar `consume`, `random` o `repeat`.
- Actualización instantánea (MPD `idle` → SSE).
- OLED y navegación con botones.

## Data model

**Core** (`src/OpenPlayer.Core/`):

```csharp
// Models/LibraryEntry.cs — Id solo en la cola (playlistinfo); null en biblioteca y playlists
public sealed record LibraryEntry(string Uri, Track? Track, int? Id = null);

// Interfaces/IQueue.cs — tres métodos nuevos
Task RemoveAsync(int id, CancellationToken ct = default);          // deleteid ID
Task MoveAsync(int id, int to, CancellationToken ct = default);    // moveid ID TO (TO = posición destino, 0-based)
Task ClearAsync(CancellationToken ct = default);                   // clear

// Messages/IpcMessage.cs
public sealed record QueueRemoveRequested(int Id) : IpcMessage;
public sealed record QueueMoveRequested(int Id, int To) : IpcMessage;
public sealed record QueueClearRequested : IpcMessage;
```

- `Id` lo asigna MPD a cada pista de la cola y no cambia al mover ni al quitar otras.

**Validación (Core, al parsear):** `id` y `to` son enteros JSON ≥ 0 y obligatorios. Inválido → `error` con `request`, como en SPEC 10.

**Mensajes IPC** (`architecture.md` §7; todos responden `ok` o `error`):

```json
{"type":"queue.remove","id":17}
{"type":"queue.move","id":17,"to":2}
{"type":"queue.clear"}
```

`queue.page` suma `id` en cada entrada:

```json
{"type":"queue.page","playlist":"Favoritas","offset":0,"total":1,"entries":[{"uri":"A1.flac","id":17,"title":"Rolling In The Deep","artist":"Adele","album":"21","durationSeconds":225}]}
```

**Service — nombre de la lista cargada** (se suma a la tabla de SPEC 11):

| Mensaje exitoso | Efecto |
|---|---|
| `queue.clear` | `= null` |
| `queue.remove`, `queue.move` | sin cambio |

**HTTP** (web agent; mismos errores `400` / `502` / `503` / `403` / `404` / `405` que SPEC 10):

| Método y ruta | IPC | Éxito |
|---|---|---|
| `DELETE /api/queue/tracks/{id}` | `queue.remove` | `204` |
| `POST /api/queue/move` `{"id","to"}` | `queue.move` | `204` |
| `DELETE /api/queue` | `queue.clear` | `204` |

`/api/queue` suma `DELETE` al `GET` existente.

**Página:** sin datos nuevos persistentes. Cada fila guarda el `id` de su entrada y su posición.

## Implementation plan

1. **Core: id en las entradas.**
   - `LibraryEntry` suma `Id` (opcional, al final; los usos existentes compilan sin cambios).
   - `QueuePageMessage` serializa `id` en cada entrada.
   - Pruebas: JSON exacto de `queue.page` con `id`; `id` `null` explícito si falta.
2. **Mpd: leer `Id`.**
   - `MpdEntryParser` toma `Id` de cada pista (entero; ausente o inválido → `null`).
   - Pruebas: `playlistinfo` con `Id` lo trae; `lsinfo` y `listplaylistinfo` dejan `null`.
3. **Core: mensajes de edición.**
   - `IQueue` suma `RemoveAsync`, `MoveAsync`, `ClearAsync`.
   - `QueueRemoveRequested`, `QueueMoveRequested`, `QueueClearRequested`, su parseo y su alta en los tipos que responden.
   - Pruebas: los tres válidos; `id` o `to` faltante, `-1`, `"3"`, `3.5` inválidos con `request`.
4. **Mpd: `MpdQueue`.**
   - `RemoveAsync` (`deleteid ID`), `MoveAsync` (`moveid ID TO`), `ClearAsync` (`clear`); negativos lanzan sin abrir conexión.
   - Pruebas con `FakeMpdServer`: comando exacto por método; `ACK` de id inexistente.
5. **Service.**
   - `IpcServer` atiende los tres mensajes; `queue.clear` exitoso pone `_loadedPlaylist` en `null`.
   - Pruebas con fakes: cada mensaje llama al método correcto; tras `playlist.play` + `queue.clear`, `queue.get` trae `playlist` `null`; tras `queue.remove` o `queue.move` el nombre sigue; un `queue.clear` que falla no lo cambia; un error de MPD llega como `error` y la conexión sigue.
6. **Web agent.**
   - `ipc.py`: `remove_from_queue(id)`, `move_in_queue(id, to)`, `clear_queue()`.
   - `server.py`: `DELETE /api/queue/tracks/{id}`, `POST /api/queue/move`, `DELETE /api/queue`.
   - Pruebas: línea exacta enviada; `204`; cada `400` (`id` en la ruta no numérico, `id`/`to` faltante/negativo/no entero/bool); `502`; `503`; `405`.
7. **`index.html`: editar la cola.**
   - ↑ / ↓ / ✕ en cada fila del panel; ↑ deshabilitado en la primera fila, ↓ en la última de la cola.
   - ↑/↓ → `POST /api/queue/move` con `{ id, to: pos ∓ 1 }`; ✕ → `DELETE /api/queue/tracks/{id}`.
   - "Limpiar" en el encabezado con `confirm("¿Limpiar la cola? Se detiene la reproducción.")` → `DELETE /api/queue`; oculto con la cola vacía.
   - Tras éxito: `reloadQueue()`. Errores en el mensaje del panel, como en SPEC 11.
8. **Docs.**
   - `architecture.md` §5 (rutas, controles del panel), §6 (`IQueue`, `LibraryEntry.Id`), §7 (mensajes, `id` en `queue.page`, `clear` y el nombre).
   - README (editar la cola).
9. **Verificación en la Pi:** deploy, criterios de la sección siguiente desde PC y móvil.

Cada paso deja `dotnet test` y `pytest` en verde.

## Acceptance criteria

**Windows (automatizable):**

- [ ] `dotnet test`, `pytest tests/web-agent` y `pytest tests/hardware-agent` pasan.
- [ ] `queue.page` incluye `id` en cada entrada con el valor de `Id:` de `playlistinfo`; las respuestas de `library.page` y `playlist.get` no cambian.
- [ ] `IpcMessageParser` devuelve `QueueRemoveRequested(17)`, `QueueMoveRequested(17, 2)` y `QueueClearRequested`; `id` o `to` faltante, `-1`, `"3"` o `3.5` son inválidos con su `request`.
- [ ] `MpdQueue` envía exactamente `deleteid 17`, `moveid 17 2` y `clear`; un `ACK` llega como `error` y la conexión sigue.
- [ ] Tras `playlist.play` de "Viaje", `queue.remove` y `queue.move` dejan `"playlist":"Viaje"`; `queue.clear` lo deja en `null`; un `queue.clear` que falla no lo cambia.
- [ ] `DELETE /api/queue/tracks/17` → `204` y llega `remove_from_queue(17)`; `POST /api/queue/move` con `{"id":17,"to":2}` → `204`; `DELETE /api/queue` → `204`; `id` o `to` inválidos → `400`; Service `error` → `502`; Service caído → `503`; método incorrecto → `405`.
- [ ] El web agent sigue usando solo stdlib.

**Raspberry Pi (`deploy.ps1` y navegador en PC y móvil):**

- [ ] Cada fila del panel muestra ↑ / ↓ / ✕; ↑ está deshabilitado en la primera y ↓ en la última.
- [ ] ↓ en la fila 2 la deja en la posición 3, igual que `mpc playlist`; ↑ la devuelve.
- [ ] ✕ en una fila que no es la actual la quita y la reproducción sigue sin cortes.
- [ ] ✕ en la pista actual mientras suena pasa a la siguiente.
- [ ] Mover la pista actual mantiene el resaltado sobre ella en su nueva posición.
- [ ] "Limpiar" pide confirmación; al aceptar, la reproducción se detiene, el panel muestra "Cola vacía", el encabezado dice "Cola" y "Limpiar" se oculta; al cancelar, nada cambia.
- [ ] Tras quitar o mover en una lista reproducida, el encabezado sigue diciendo "Lista: <nombre>" y la lista guardada no cambia en Listas.
- [ ] Con la cola cambiada desde `mpc` justo antes, ✕ quita la pista mostrada (por id) o muestra el error de MPD si ya no existe; nunca quita otra pista.
- [ ] Tocar la fila sigue reproduciéndola; los botones ↑ / ↓ / ✕ no la reproducen.

**Documentación:**

- [ ] `architecture.md` §5, §6 y §7 describen las rutas, `IQueue`, `LibraryEntry.Id`, los mensajes y el efecto de `clear` sobre el nombre.
- [ ] README menciona que la cola se edita desde el panel.

## Decisions

**Tomadas:**

- **Editar por id de MPD (`deleteid`, `moveid`), no por posición.** La cola cambia más que una lista guardada (fin de canción, `mpc`, otra pestaña); con el sondeo de 2 s una posición vieja puede quitar otra pista. El id no cambia al mover ni al quitar otras: lo peor es un `ACK` de id inexistente.
- **`Id` opcional en `LibraryEntry`.** La cola ya reutiliza `LibraryPage`; un campo `null` fuera de la cola evita un modelo paralelo. `library.page` y `playlist.get` no lo serializan.
- **↑ / ↓ / ✕ en cada fila, como en Listas.** Mismo patrón y mismo helper `row()` de SPEC 10; funciona en táctil y teclado.
- **"Limpiar" en el encabezado con `confirm()` nativo.** Única acción destructiva de la cola; mismo criterio que borrar una lista en SPEC 10.
- **Limpiar pone el nombre de la lista cargada en `null`.** La cola vacía ya no es esa lista.
- **Quitar y mover no cambian el nombre.** La lista guardada no se toca; "Lista: X" sigue indicando de dónde vino la cola.
- **Recargar la cola tras cada operación (`reloadQueue()`).** Mismo camino que SPEC 11 al cambiar `queueVersion`; posiciones y deshabilitados siempre coherentes.
- **Quitar la pista actual se deja a MPD.** Pasa a la siguiente sin código propio.

**Descartadas:**

- **Editar por posición (`delete N`, `move A B`).** Consistente con SPEC 10 pero riesgoso con una cola viva.
- **Enviar el `queueVersion` esperado y rechazar si cambió.** Más estado y mensajes; el id ya cubre el caso que importa.
- **Botón "Editar" que muestra los controles.** Más UI y un modo; las filas de Listas ya muestran los botones siempre.
- **"Lista: X (modificada)" o pasar a "Cola" al editar.** Pedido del usuario: mantener el nombre; solo `clear` lo borra.
- **Agregar a la cola sin reemplazarla.** Otro flujo en Biblioteca y Listas; spec futura.
- **Arrastrar y soltar.** No funciona en táctil sin librería (SPEC 10).

## Risks

| Riesgo | Mitigación |
|---|---|
| Panel angosto (900–1000 px o móvil) con ↑ / ↓ / ✕ además de número, ícono y duración | Mismos botones compactos de Listas; el título se corta con elipsis. Verificado en el criterio de la Pi en PC y móvil. |
| Tocar ↑/↓ varias veces rápido usa la posición de antes de recargar | `moveid` lleva el id correcto; el destino puede quedar corrido una posición hasta la recarga. Aceptado. |
| Quitar la última pista mientras suena detiene la reproducción | Comportamiento de MPD; la página muestra el nuevo estado en el siguiente sondeo. |
| Recargar tras editar descarta las páginas cargadas con "Más" | Se vuelven a cargar desde 0 hasta la actual (SPEC 11); editar lejos de la actual requiere "Más" otra vez. Aceptado. |
| Cualquiera en la LAN puede limpiar la cola | Igual que reproducir, que ya reemplaza la cola (SPEC 10); solo LAN y con confirmación. |

## What is **not** in this spec

- Agregar a la cola sin reemplazarla.
- Guardar la cola como playlist.
- Marcar la lista como "modificada".
- Arrastrar y soltar.
- Deshacer.
- Cambiar `consume`, `random` o `repeat`.
- Actualización instantánea (MPD `idle` → SSE).
- OLED y navegación con botones.

Cada uno, si llega, va en su propia spec.
