# SPEC 11 — Cola de reproducción en la web

> **Status:** Implemented
> **Depends on:** SPEC 03, SPEC 08, SPEC 09, SPEC 10
> **Date:** 2026-10-21
> **Objective:** Mostrar en la página del web agent la cola actual de MPD (panel a la derecha en pantallas anchas, debajo de los controles en el móvil) con el nombre de la lista cargada, filas con título, artista, álbum y duración en orden, la pista actual resaltada con un ícono animado que se detiene en pausa, y tocar una fila para saltar a esa pista.

## Scope

**In:**

- Core:
  - `PlaybackSnapshot` suma `QueuePosition` (int?, índice 0-based de la pista actual) y `QueueVersion` (long?); `player.snapshot` los serializa como `queuePosition` y `queueVersion`.
  - Contrato `IQueue` (`GetAsync(offset)`, `PlayAsync(position)`) en `src/OpenPlayer.Core/Interfaces/`.
  - Mensajes IPC `queue.get` (responde `queue.page`) y `queue.play` (responde `ok`), con su parseo y el serializador `QueuePageMessage`.
- Mpd:
  - `MpdSnapshotParser` lee `song` y `playlist` de `status`.
  - `MpdQueue`: `playlistinfo` paginado de 100 en el adaptador, `play N`.
- Service:
  - `IpcServer` atiende `queue.get` / `queue.play` bajo el mismo lock.
  - Recuerda en memoria el nombre de la lista cargada: lo fija `playlist.play`, lo borra `library.play`, lo actualiza `playlist.rename` y lo borra `playlist.delete` de esa lista. Se pierde al reiniciar el Service.
- Web agent:
  - `ipc.py`: `queue(offset)` y `play_queue(position)`.
  - `server.py`: `GET /api/queue?offset=` y `POST /api/queue/play` `{"position"}`.
  - `index.html`:
    - Panel "Cola" fijo a la derecha en todas las pestañas (≥ 900 px); en pantallas angostas, debajo de los controles de la pestaña Reproductor.
    - Encabezado "Lista: <nombre>" o "Cola" + "· N canciones".
    - Filas propias: número, título (o nombre de archivo), "artista · álbum" si existen, m:ss.
    - Pista actual con color propio y 3 barras animadas en CSS: congeladas en pausa, sin ícono en `stopped`, quietas con `prefers-reduced-motion`.
    - Se recarga solo cuando cambia `queueVersion`; carga páginas desde 0 hasta incluir la pista actual, luego "Más".
    - Auto-scroll a la pista actual salvo que el usuario esté desplazando el panel.
    - Tocar una fila → `queue.play`.
    - "Cola vacía" sin pistas.
    - Pestaña Listas (corrige SPEC 10): al volver a la pestaña se recarga lo que muestra (la lista abierta, con las pistas que había cargadas, o el índice), para ver lo agregado desde Biblioteca.
- Pruebas: Core (parser, snapshot, serializador), Mpd (`status`, `playlistinfo`, `play N`), Service (nombre recordado en cada caso), web agent (ipc + HTTP).
- Docs: `architecture.md` §5, §6, §7; README; en SPEC 10 cambiar "SPEC 11" (OLED + botones) por "spec futura".

**Out of scope (for future specs):**

- Editar la cola: quitar, reordenar, agregar, limpiar.
- Persistir el nombre de la lista entre reinicios del Service.
- Detectar la lista comparando la cola con las playlists guardadas.
- Cambiar el modo `consume`, `random` o `repeat` de MPD (el historial depende de `consume` apagado, el valor por defecto).
- Atenuar las pistas ya escuchadas.
- Actualización instantánea (MPD `idle` → SSE); sigue el sondeo de 2 s.
- OLED y navegación con botones.

## Data model

**Core** (`src/OpenPlayer.Core/`):

```csharp
// Models/PlaybackSnapshot.cs — dos campos nuevos al final (null sin pista / MPD sin dato)
public sealed record PlaybackSnapshot(
    PlaybackState State, Track? CurrentTrack, TimeSpan? Position, TimeSpan? Duration, int? Volume,
    DateTimeOffset UpdatedAt, int? QueuePosition = null, long? QueueVersion = null);

// Interfaces/IQueue.cs
public interface IQueue
{
    Task<LibraryPage> GetAsync(int offset, CancellationToken ct = default);  // playlistinfo; posición = Offset + índice
    Task PlayAsync(int position, CancellationToken ct = default);           // play N
}

// Messages/IpcMessage.cs
public sealed record QueueGetRequested(int Offset) : IpcMessage;
public sealed record QueuePlayRequested(int Position) : IpcMessage;
```

- `QueuePosition` viene de `status: song` (0-based) y `QueueVersion` de `status: playlist` (MPD lo incrementa en cada cambio de la cola).
- `LibraryPage` se reutiliza: en la cola, todas las entradas son pistas.

**Validación (Core, al parsear):** `queue.get` → `offset` entero JSON ≥ 0, opcional (0). `queue.play` → `position` entero JSON ≥ 0, obligatorio. Inválido → `error` con `request`, como en SPEC 10.

**Mensajes IPC** (`architecture.md` §7; ambos responden una línea):

```json
{"type":"queue.get","offset":0}
{"type":"queue.play","position":3}
```

Respuestas:

```json
{"type":"queue.page","playlist":"Favoritas","offset":0,"total":2,"entries":[{"uri":"A1.flac","title":"Rolling In The Deep","artist":"Adele","album":"21","durationSeconds":225},{"uri":"x.mp3","title":null,"artist":null,"album":null,"durationSeconds":null}]}
{"type":"ok","request":"queue.play"}
```

- `playlist`: el nombre recordado o `null`. Entradas con los mismos campos que una pista de `library.page`, sin `directory`.

`player.snapshot` suma dos campos (siempre presentes, `null` explícito si faltan):

```json
{"type":"player.snapshot","state":"playing","trackTitle":"X","trackArtist":"A","positionSeconds":42,"durationSeconds":210,"volume":35,"queuePosition":3,"queueVersion":42}
```

**Service — nombre de la lista cargada** (campo `string? _loadedPlaylist` en `IpcServer`, en memoria, protegido por `_commandLock`):

| Mensaje exitoso | Efecto |
|---|---|
| `playlist.play` | `= name` |
| `library.play` | `= null` |
| `playlist.rename` con `name == _loadedPlaylist` | `= newName` |
| `playlist.delete` con `name == _loadedPlaylist` | `= null` |
| Reinicio del Service | `null` |

Un mensaje que falla no cambia el nombre.

**HTTP** (web agent; se suma al contrato de SPEC 10, mismos errores `400` / `502` / `503` / `403` / `404` / `405`):

| Método y ruta | IPC | Éxito |
|---|---|---|
| `GET /api/queue?offset=` | `queue.get` | `200` `queue.page` |
| `POST /api/queue/play` `{"position"}` | `queue.play` | `204` |

**Página:** sin datos persistentes. Guarda en memoria el último `queueVersion` cargado y las filas cargadas; recarga cuando el snapshot trae otro `queueVersion`.

## Implementation plan

1. **Core: snapshot.**
   - `QueuePosition` y `QueueVersion` en `PlaybackSnapshot` (opcionales, al final; los usos existentes compilan sin cambios).
   - `SnapshotMessage` los serializa con `null` explícito.
   - Pruebas: snapshot completo exacto con los dos campos; `null` explícitos.
2. **Mpd: snapshot.**
   - `MpdSnapshotParser` lee `song` y `playlist` de `status`; valores ausentes o no numéricos → `null`.
   - Pruebas con respuestas de `status` con y sin esos campos.
3. **Core: mensajes de cola.**
   - `IQueue`, `QueueGetRequested`, `QueuePlayRequested`, su parseo (y `queue.get`/`queue.play` en los tipos que responden).
   - `QueuePageMessage.Serialize(LibraryPage, string? playlist)`.
   - Pruebas: ambos mensajes válidos; `offset` opcional; `position` faltante, `-1`, `"3"`, `3.5` inválidos con `request`; JSON exacto de `queue.page` con y sin `playlist`.
4. **Mpd: `MpdQueue`.**
   - `GetAsync` (`playlistinfo`, paginado con `MpdEntryParser`), `PlayAsync` (`play N`).
   - Pruebas con `FakeMpdServer`: 120 pistas → 100 + 20, metadatos faltantes, comando exacto, `ACK`.
5. **Service.**
   - `IpcServer` atiende `queue.get` / `queue.play`; `Program.cs` registra `IQueue → MpdQueue`.
   - `_loadedPlaylist` según la tabla del modelo de datos.
   - Pruebas con fakes: `queue.page` trae `playlist` tras `playlist.play`; `null` tras `library.play`; renombrar y borrar la lista cargada; renombrar otra no la cambia; un `playlist.play` que falla no la cambia.
6. **Web agent.**
   - `ipc.py`: `queue(offset)`, `play_queue(position)`.
   - `server.py`: `GET /api/queue`, `POST /api/queue/play`.
   - Pruebas: línea exacta enviada; `200`, `204`, cada `400` (`offset` inválido, `position` faltante/negativo/no entero/bool), `502`, `503`, `405`.
7. **`index.html`: layout y panel.**
   - Panel "Cola" con encabezado y filas propias; a la derecha ≥ 900 px y en todas las pestañas, debajo de los controles en pantallas angostas.
   - Carga inicial y al cambiar `queueVersion`: páginas desde 0 hasta incluir `queuePosition`, luego "Más".
   - "Cola vacía"; errores con los mismos mensajes que SPEC 10.
8. **`index.html`: pista actual.**
   - Color propio y barras animadas en CSS (`animation-play-state: paused` en pausa, sin ícono en `stopped`, quietas con `prefers-reduced-motion`).
   - Se actualiza en cada sondeo sin recargar la cola.
   - Auto-scroll a la pista actual, salvo durante 10 s después de que el usuario desplace el panel.
   - Tocar una fila → `POST /api/queue/play` y `refresh()`.
   - Pestaña Listas: cada vez que se abre (no solo la primera), recargar la lista abierta (`loadPlaylist(true)`) o el índice (`showIndex()`).
9. **Docs.**
   - `architecture.md` §5 (layout, rutas), §6 (`IQueue`), §7 (mensajes, campos del snapshot, nombre en memoria).
   - README (panel de cola; historial depende de `consume` apagado).
   - SPEC 10: "SPEC 11" → "spec futura".
10. **Verificación en la Pi:** deploy, criterios de la sección siguiente desde PC y móvil.

Cada paso deja `dotnet test` y `pytest` en verde.

## Acceptance criteria

**Windows (automatizable):**

- [x] `dotnet test`, `pytest tests/web-agent` y `pytest tests/hardware-agent` pasan.
- [x] `player.snapshot` incluye `queuePosition` y `queueVersion` con los valores de `status: song` y `status: playlist`, y `null` explícito si MPD no los da.
- [x] `IpcMessageParser` devuelve `QueueGetRequested(0)` sin `offset` y `QueuePlayRequested(3)` con `position` 3; `position` faltante, `-1`, `"3"` o `3.5` son inválidos con `request` `queue.play`.
- [x] `QueuePageMessage` produce exactamente el JSON del modelo de datos, con `playlist` `null` cuando no hay nombre.
- [x] `MpdQueue.GetAsync` sobre 120 pistas devuelve `total` 120 y 100 entradas; `offset` 100 devuelve 20. `PlayAsync(3)` envía `play 3`.
- [x] Tras `playlist.play` de "Viaje", `queue.get` trae `"playlist":"Viaje"`; tras `library.play`, `null`.
- [x] Renombrar "Viaje" (la cargada) a "Gym" hace que `queue.get` traiga "Gym"; renombrar otra lista no la cambia; borrar "Gym" la deja en `null`; un `playlist.play` que falla no la cambia.
- [x] Un `ACK` de MPD en `queue.get` o `queue.play` llega como `error` y la conexión sigue.
- [x] `GET /api/queue` → `200`; `POST /api/queue/play` con `{"position":3}` → `204` y llega `play_queue(3)`; `offset` o `position` inválidos → `400`; Service `error` → `502`; Service caído → `503`; método incorrecto → `405`.
- [x] El web agent sigue usando solo stdlib.

**Raspberry Pi (`deploy.ps1` y navegador en PC y móvil):**

- [x] En PC (ventana ≥ 900 px) el panel "Cola" aparece a la derecha en las tres pestañas; en el móvil aparece debajo de los controles en Reproductor.
- [x] Reproducir "Favoritas" muestra "Lista: Favoritas · N canciones" con las pistas en el orden de `mpc playlist`; reproducir una pista de la biblioteca muestra "Cola · 1 canción".
- [x] Cada fila muestra número, título, "artista · álbum" y m:ss; una pista sin etiquetas muestra el nombre de archivo y sin detalle.
- [x] La pista actual tiene un color distinto y las barras se mueven; en pausa las barras quedan quietas; detenido no hay barras.
- [x] Al pasar a la siguiente pista (botón o fin de canción), el resaltado se mueve en 2 s o menos y la pista anterior sigue en la lista.
- [x] Tocar la cuarta fila deja `mpc status` en la posición #4.
- [x] Con más de 100 pistas en la cola y la actual pasada la 100, la actual aparece cargada y visible sin tocar "Más".
- [x] Desplazar el panel lejos de la actual no lo hace saltar de vuelta durante 10 s.
- [x] Con una lista abierta en Listas, agregarle una pista desde Biblioteca y volver a Listas la muestra sin salir y entrar de la lista.
- [x] Renombrar la lista en reproducción actualiza el encabezado; reiniciar el Service lo deja en "Cola".
- [x] Con el Service detenido, el panel muestra "Sin conexión con el reproductor" y se recupera al reiniciarlo, sin recargar la página.
- [x] La cola no se vuelve a pedir mientras `queueVersion` no cambia (verificable en `journalctl -u openplayer`: sin `queue.get ok` en cada sondeo).

**Documentación:**

- [x] `architecture.md` §5, §6 y §7 describen panel, rutas, `IQueue`, mensajes, campos del snapshot y el nombre en memoria.
- [x] README menciona el panel de cola y que el historial depende de `consume` apagado.
- [x] SPEC 10 ya no reserva "SPEC 11".

## Decisions

**Tomadas:**

- **Nombre de la lista recordado en memoria por el Service.** MPD no guarda qué playlist se cargó; el Service ve cada `playlist.play` y `library.play`. Se pierde al reiniciar y puede quedar viejo si la cola cambia por `mpc`: aceptado.
- **Renombrar la lista cargada actualiza el nombre; borrarla lo limpia.** Agregar o quitar pistas de la lista guardada no toca la cola (en MPD son independientes) y no cambia el nombre.
- **`queuePosition` y `queueVersion` en `player.snapshot`.** El sondeo de 2 s ya existe; el resaltado se mueve sin pedir la cola, y la cola se pide solo cuando MPD cambia su versión (`status: playlist`).
- **`queue.get` paginado de 100, reutilizando `LibraryPage` y `MpdEntryParser`.** Mismo patrón que SPEC 10; una cola de 1000 pistas no viaja entera.
- **Cargar páginas desde 0 hasta incluir la pista actual.** Siempre se puede resaltar y desplazar a la actual; solo cuesta al cambiar la cola.
- **Contrato propio `IQueue`.** La cola no es la biblioteca ni las playlists guardadas; mantiene `ILibrary` e `IPlaylistStore` como en SPEC 10.
- **Panel a la derecha ≥ 900 px en todas las pestañas; debajo de los controles en el móvil.** En pantalla ancha hay espacio de sobra; en el móvil no hay "derecha" y una cuarta pestaña escondería la cola.
- **Tocar una fila salta a esa pista (`play N`).** Un comando; coherente con tocar pistas en Biblioteca y Listas.
- **Auto-scroll pausado 10 s tras desplazar el panel a mano.** El panel sigue a la pista actual sin pelear con el usuario.
- **Barras de ecualizador en CSS puro.** `animation-play-state: paused` en pausa, sin ícono en `stopped`, quietas con `prefers-reduced-motion`. Sin imágenes ni JS de animación.
- **Las pistas escuchadas no se atenúan.** Pedido del usuario; solo la actual se distingue.
- **No tocar `consume`.** Con `consume` apagado (por defecto) MPD conserva lo escuchado; se documenta en el README.
- **Tomar el número 11.** El OLED + botones (anunciado como SPEC 11 en SPEC 10) pasa a "spec futura".

**Descartadas:**

- **Persistir el nombre en un archivo.** Más estado en disco para un dato que igual puede quedar viejo por `mpc`.
- **Detectar la lista comparando la cola con cada playlist guardada.** Caro (una consulta por lista) y ambiguo si dos listas coinciden.
- **Cargar solo la página de la pista actual con "Anteriores"/"Más".** Más UI y estado para un caso raro.
- **Cola entera sin paginar.** ~300 KB por cada cambio con colas grandes.
- **Cuarta pestaña "Cola" en el móvil.** Esconde la cola del reproductor.
- **Editar la cola (quitar, reordenar, limpiar).** Otro conjunto de mensajes y UI; spec futura.
- **Pedir la cola en cada sondeo.** Carga innecesaria a MPD; `queueVersion` lo evita.

## Risks

| Riesgo | Mitigación |
|---|---|
| El nombre queda viejo si la cola cambia fuera de la web (`mpc load`, `mpc clear`, botones futuros) | Aceptado: el encabezado puede mostrar una lista que ya no está cargada. Se corrige con el próximo `playlist.play` o `library.play` desde la web. |
| `consume` encendido borra lo escuchado | No se toca; README documenta que el historial depende de `consume` apagado. |
| Cola grande y pista actual lejos (p. ej. #900 de 1000): 10 pedidos al cambiar la cola | Solo ocurre cuando cambia `queueVersion`; cada página ~30 KB. Si pesa, pedir directo la página de la actual en otra spec. |
| `queueVersion` cambia entre pedidos de páginas (otra pestaña o `mpc` editó la cola) | La página compara la versión del siguiente snapshot y recarga; puede mostrar una cola mezclada hasta 2 s. |
| Tocar una fila con una cola vieja salta a otra pista | Ventana ≤ 2 s (sondeo); MPD responde `ACK` si la posición ya no existe y la página lo muestra. |
| `random` encendido: el orden de reproducción no es el de la cola | La lista muestra el orden de la cola de MPD y el resaltado sigue a `song`; el salto entre filas puede verse no secuencial. Aceptado y documentado. |
| Panel fijo a la derecha apretado entre 900 y ~1000 px | El reproductor mantiene su ancho máximo de 420 px y el panel toma el resto con un mínimo; por debajo de 900 px pasa abajo. |

## What is **not** in this spec

- Editar la cola (quitar, reordenar, agregar, limpiar).
- Persistir el nombre de la lista o detectarlo comparando con las playlists.
- Cambiar `consume`, `random` o `repeat`.
- Atenuar las pistas escuchadas.
- Actualización instantánea (MPD `idle` → SSE).
- OLED y navegación con botones.

Cada uno, si llega, va en su propia spec.
