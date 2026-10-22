# SPEC 13 — Agregar a la cola y guardar la cola como lista

> **Status:** Implemented
> **Depends on:** SPEC 10, SPEC 11, SPEC 12
> **Date:** 2026-10-22
> **Objective:** Cambiar el "+" de cada pista o carpeta de la Biblioteca por un menú (Reproducir siguiente, Agregar a la cola, Agregar a una lista ›) que agrega a la cola sin reemplazarla, y permitir guardar la cola actual como una lista de MPD desde el panel "Cola".

## Scope

**In:**

- Core:
  - `IQueue` suma `AddAsync(uri, next)` y `SaveAsync(name)`.
  - Mensajes IPC `queue.add` (`uri`, `next` opcional, `false`) y `queue.save` (`name`), con su parseo; responden `ok`.
- Mpd (`MpdQueue`):
  - `AddAsync(uri, next: false)` → `add "<uri>"` (al final).
  - `AddAsync(uri, next: true)` → `status` y, con pista actual, `add "<uri>" <song+1>`; sin pista actual, `add "<uri>"`.
  - `SaveAsync(name)` → `save "<name>"`; si ya existe, el `ACK` de MPD llega como `error`.
- Service:
  - `IpcServer` atiende `queue.add` y `queue.save` bajo el mismo lock.
  - `queue.add` no cambia el nombre de la lista cargada; `queue.save` exitoso lo fija al nombre guardado.
- Web agent:
  - `ipc.py`: `add_to_queue(uri, next)`, `save_queue(name)`.
  - `server.py`: `POST /api/queue/tracks` `{"uri","next"}`, `POST /api/queue/save` `{"name"}`.
  - `index.html`, Biblioteca (carpetas, búsqueda y resultados):
    - Tocar una pista sigue reemplazando la cola y reproduciéndola; tocar una carpeta sigue abriéndola.
    - "+" abre un menú (`<dialog>`) con el nombre de la entrada y: "Reproducir siguiente", "Agregar a la cola", "Agregar a una lista ›".
    - "Agregar a una lista ›" reemplaza el contenido del menú por las listas guardadas y "‹ Atrás".
    - Mensaje tras cada acción: "Sonará a continuación: <título>", "Agregado a la cola: <título>", "Agregado a “<lista>”".
  - `index.html`, panel "Cola":
    - Botón "Guardar como lista" junto a "Limpiar" (oculto con la cola vacía); `prompt` del nombre → `POST /api/queue/save`.
    - Éxito: "Cola guardada como “<nombre>”" y el encabezado pasa a "Lista: <nombre>".
- Pruebas: Core (parser), Mpd (comandos exactos con y sin pista actual, `ACK` de nombre existente), Service (nombre tras `add` y `save`), web agent (ipc + HTTP).
- Docs: `architecture.md` §5, §6, §7, §9; README.

**Out of scope (for future specs):**

- Reproducir siguiente / agregar a la cola desde Listas (pistas de una lista abierta o la lista entera).
- Sobrescribir una lista existente al guardar la cola.
- Arrastrar para reordenar (pendiente en `architecture.md` §9).
- Cambios en ↑/↓/✕ y "Limpiar" de la cola (SPEC 12 sin cambios).
- Menú contextual con clic derecho o pulsación larga.
- Actualización instantánea (MPD `idle` → SSE).
- OLED y navegación con botones.

## Data model

**Core** (`src/OpenPlayer.Core/`):

```csharp
// Interfaces/IQueue.cs — dos métodos nuevos
Task AddAsync(string uri, bool next, CancellationToken ct = default);  // pista o carpeta (recursivo); next = después de la actual
Task SaveAsync(string name, CancellationToken ct = default);           // save NAME; existe → MpdException

// Messages/IpcMessage.cs
public sealed record QueueAddRequested(string Uri, bool Next) : IpcMessage;
public sealed record QueueSaveRequested(string Name) : IpcMessage;
```

**Validación (Core, al parsear):**

| Campo | Regla |
|---|---|
| `uri` | 1–1024 caracteres, sin caracteres de control (igual que `library.play`) |
| `next` | booleano JSON, opcional (`false`); `"true"`, `1` o `null` son inválidos |
| `name` | `PlaylistName.EnsureValid` (SPEC 10) |

Inválido → `error` con `request`, como en SPEC 10.

**Mensajes IPC** (`architecture.md` §7; ambos responden `ok` o `error`):

```json
{"type":"queue.add","uri":"Rock/AC DC/01.flac","next":true}
{"type":"queue.add","uri":"Rock/AC DC"}
{"type":"queue.save","name":"Viaje"}
```

**MPD** (`MpdQueue`; "Reproducir siguiente" usa dos conexiones, `status` y luego `add`, como `MpdPlaylistStore.CreateAsync`):

| Llamada | Comandos |
|---|---|
| `AddAsync(uri, false)` | `add "<uri>"` |
| `AddAsync(uri, true)` con `status: song` = N | `status`, luego `add "<uri>" N+1` |
| `AddAsync(uri, true)` sin `song` (cola vacía o detenida sin actual) | `status`, luego `add "<uri>"` |
| `SaveAsync(name)` | `save "<name>"` |

- `add` con posición requiere MPD ≥ 0.23.3; una carpeta se inserta completa, en orden, a partir de esa posición.

**Service — nombre de la lista cargada** (se suma a las tablas de SPEC 11 y 12):

| Mensaje exitoso | Efecto |
|---|---|
| `queue.add` | sin cambio |
| `queue.save` | `= name` |

**HTTP** (web agent; mismos errores `400` / `502` / `503` / `403` / `404` / `405` que SPEC 10):

| Método y ruta | IPC | Éxito |
|---|---|---|
| `POST /api/queue/tracks` `{"uri","next"}` | `queue.add` | `204` |
| `POST /api/queue/save` `{"name"}` | `queue.save` | `204` |

- `next` opcional; si viene, debe ser booleano JSON (si no, `400`).

**Página:** sin datos persistentes. El menú guarda en memoria la entrada elegida (`uri`, título o nombre de carpeta) mientras está abierto.

## Implementation plan

1. **Verificar MPD en la Pi.**
   - `mpd --version` ≥ 0.23.3; `mpc insert` o `echo 'add "<pista>" 1' | nc localhost 6600` inserta en la posición 1.
   - Si es menor, parar y revisar la spec (no hay `add` con posición).
2. **Core: mensajes.**
   - `QueueAddRequested`, `QueueSaveRequested`, su parseo y su alta en los tipos que responden.
   - Pruebas: válidos (`next` true, false y ausente); `uri` vacía o con control, `next` `"true"`/`1`/`null`, `name` inválido → inválidos con `request`.
3. **Mpd: `MpdQueue`.**
   - `IQueue` suma `AddAsync` y `SaveAsync`; `MpdQueue` los implementa según la tabla del modelo de datos; `FakeLibrary` (pruebas del Service) los registra.
   - Pruebas con `FakeMpdServer`: `add "<uri>"`; `status` con `song: 2` → `add "<uri>" 3`; `status` sin `song` → `add "<uri>"`; comillas escapadas; `save "<name>"`; `ACK` de lista existente → `MpdException`.
4. **Service.**
   - `IpcServer` atiende `queue.add` y `queue.save`; `queue.save` exitoso fija `_loadedPlaylist`.
   - Pruebas con fakes: cada mensaje llama al método correcto; tras `playlist.play` de "Viaje" + `queue.add`, `queue.get` trae "Viaje"; tras `queue.save` de "Gym", "Gym"; un `queue.save` que falla no lo cambia.
5. **Web agent.**
   - `ipc.py`: `add_to_queue(uri, next)`, `save_queue(name)`.
   - `server.py`: `POST /api/queue/tracks`, `POST /api/queue/save`.
   - Pruebas: línea exacta enviada; `204`; `400` (`uri` faltante/vacía, `next` no booleano, `name` faltante/vacío); `502`; `503`; `405` (`GET /api/queue/tracks`, `GET /api/queue/save`).
6. **`index.html`: menú "+" de la Biblioteca.**
   - `<dialog>` con el nombre de la entrada y "Reproducir siguiente", "Agregar a la cola", "Agregar a una lista ›", "Cancelar".
   - "Agregar a una lista ›" muestra las listas y "‹ Atrás" en el mismo diálogo (reemplaza al selector de SPEC 10).
   - Cada acción cierra el menú y muestra su mensaje en la Biblioteca; errores con los mensajes de SPEC 10. Tras agregar a la cola, `refresh()` (la cola se recarga por `queueVersion`).
7. **`index.html`: "Guardar como lista".**
   - Botón junto a "Limpiar" en el encabezado de la cola, oculto con la cola vacía.
   - `prompt("Nombre de la nueva lista")` → `POST /api/queue/save`; éxito: mensaje en el panel y `reloadQueue()` (el nombre cambia sin que cambie `queueVersion`).
8. **Docs.**
   - `architecture.md` §5 (menú, botón, rutas), §6 (`IQueue`), §7 (mensajes, `add` con posición y MPD ≥ 0.23.3, nombre tras `save`), §9 (hecho / pendiente).
   - README (menú "+" y guardar la cola).
9. **Verificación en la Pi:** deploy, criterios de la sección siguiente desde PC y móvil.

Cada paso deja `dotnet test` y `pytest` en verde.

## Acceptance criteria

**Windows (automatizable):**

- [x] `dotnet test`, `pytest tests/web-agent` y `pytest tests/hardware-agent` pasan.
- [x] `IpcMessageParser` devuelve `QueueAddRequested("a.flac", true)`, `QueueAddRequested("a.flac", false)` sin `next` y `QueueSaveRequested("Viaje")`; `uri` vacía, `next` `"true"`/`1`/`null` y `name` inválido son inválidos con su `request`.
- [x] `MpdQueue` envía exactamente `add "a.flac"` (al final), `status` + `add "a.flac" 3` con `song: 2`, `status` + `add "a.flac"` sin `song`, y `save "Viaje"`; un `ACK` llega como `error` y la conexión sigue.
- [x] Tras `playlist.play` de "Viaje", `queue.add` deja `"playlist":"Viaje"`; `queue.save` de "Gym" lo deja en "Gym"; un `queue.save` que falla no lo cambia.
- [x] `POST /api/queue/tracks` con `{"uri":"a.flac","next":true}` → `204` y llega `add_to_queue("a.flac", True)`; sin `next` llega `False`; `POST /api/queue/save` con `{"name":"Viaje"}` → `204`; `uri`, `next` o `name` inválidos → `400`; Service `error` → `502`; Service caído → `503`; método incorrecto → `405`.
- [x] El web agent sigue usando solo stdlib.

**Raspberry Pi (`deploy.ps1` y navegador en PC y móvil):**

- [x] `mpd --version` en la Pi es ≥ 0.23.3.
- [x] Tocar una pista de la Biblioteca sigue reemplazando la cola y reproduciéndola; tocar una carpeta sigue abriéndola.
- [x] "+" en una pista, una carpeta y un resultado de búsqueda abre el menú con su nombre y las tres acciones; "Cancelar" lo cierra sin cambios.
- [x] Con la pista 3 de 10 sonando, "Reproducir siguiente" deja esa pista en la posición 4 del panel y suena al terminar la actual.
- [x] "Agregar a la cola" deja la pista al final del panel; con una carpeta, todas sus pistas al final, en orden.
- [x] "Reproducir siguiente" con una carpeta inserta todas sus pistas, en orden, después de la actual.
- [x] Con la cola vacía, "Reproducir siguiente" deja la pista como única de la cola, sin empezar a sonar.
- [x] "Agregar a una lista ›" muestra las listas y "‹ Atrás"; elegir una agrega la pista o carpeta y muestra "Agregado a “<lista>”"; "‹ Atrás" vuelve a las tres acciones.
- [x] Cada acción muestra su mensaje en la Biblioteca y el panel "Cola" refleja el cambio en 2 s o menos.
- [x] Tras agregar a la cola en una lista reproducida, el encabezado sigue diciendo "Lista: <nombre>".
- [x] "Guardar como lista" con un nombre nuevo muestra "Cola guardada como “<nombre>”", el encabezado pasa a "Lista: <nombre>" y la lista aparece en Listas con las mismas pistas y en el mismo orden que el panel.
- [x] "Guardar como lista" con un nombre que ya existe muestra el error y la lista existente no cambia; cancelar el `prompt` no hace nada.
- [x] "Guardar como lista" está oculto con la cola vacía.

**Documentación:**

- [x] `architecture.md` §5, §6, §7 y §9 describen el menú, "Guardar como lista", las rutas, `IQueue`, los mensajes, el requisito de MPD ≥ 0.23.3 y el nombre tras `save`.
- [x] README menciona el menú "+" y guardar la cola como lista.

## Decisions

**Tomadas:**

- **Tocar una pista sigue reemplazando la cola.** Pedido del usuario: el comportamiento de SPEC 10 no cambia; las acciones nuevas viven en el menú.
- **Tres acciones distintas.** Reproducir (tocar) vacía la cola; "Reproducir siguiente" inserta después de la actual; "Agregar a la cola" agrega al final. No son redundantes: solo tocar borra lo que había.
- **El "+" abre un menú en un `<dialog>`.** Una fila de móvil no tiene lugar para tres o cuatro botones; un solo "+" mantiene las filas como hoy.
- **"Agregar a una lista ›" como submenú dentro del mismo diálogo, con "‹ Atrás".** En el móvil no hay lugar para un submenú flotante al costado; reemplaza al selector de SPEC 10.
- **Carpetas y resultados de búsqueda con el mismo menú.** `add` de MPD expande carpetas recursivamente sin código propio.
- **"Reproducir siguiente" por posición absoluta: `status` + `add "<uri>" <song+1>`.** Funciona igual para pistas y carpetas, en dos conexiones (`MpdClient` envía cada lote completo antes de leer) y bajo el lock global; no depende de las posiciones relativas (`+0`), menos documentadas por versión.
- **Sin pista actual, "Reproducir siguiente" agrega al final.** No hay "siguiente" sin actual; no empieza a sonar.
- **Un solo mensaje `queue.add` con `next` opcional.** Misma validación y misma ruta HTTP para las dos acciones.
- **Agregar a la cola no cambia el nombre de la lista cargada.** Mismo criterio que quitar y mover (SPEC 12): la cola sigue viniendo de esa lista.
- **"Guardar como lista" fija el nombre de la lista cargada.** La cola es, en ese momento, exactamente esa lista.
- **`save` de MPD sin sobrescribir.** Un nombre existente da `ACK` y se muestra; nada se pisa sin querer.
- **"Guardar como lista" en el encabezado del panel, junto a "Limpiar".** Las dos acciones sobre la cola entera, en el mismo lugar; `prompt` nativo como crear una lista en SPEC 10.

**Descartadas:**

- **"Reproducir" que inserta y salta en vez de reemplazar.** El usuario prefirió mantener el reemplazo.
- **Botones separados por acción en cada fila.** Filas apretadas en el móvil.
- **Submenú flotante al costado.** No entra en una pantalla de teléfono.
- **"Reproducir siguiente" con nada sonando al principio de la cola.** Sin actual no hay "siguiente"; agregar al final es más predecible.
- **Posiciones relativas (`add "<uri>" +0`).** Mismo resultado que leer `status`, con más dependencia de la versión de MPD.
- **Sobrescribir o anexar al guardar (`save` con modo, MPD 0.24).** No está en MPD 0.23; spec futura si hace falta.
- **Agregar a la cola desde Listas.** Otro flujo; spec futura.

## Risks

| Riesgo | Mitigación |
|---|---|
| MPD de la Pi < 0.23.3: `add` no acepta posición | Paso 1 del plan lo verifica antes de escribir código; si falla, se revisa la spec (`addid` solo sirve para pistas, no carpetas). |
| La pista actual cambia entre `status` y `add` (fin de canción) | Ambos van bajo el lock global del Service (ningún otro cliente se intercala); la ventana es de milisegundos. Peor caso: la pista queda una posición más arriba. Aceptado. |
| "Reproducir siguiente" o "Agregar a la cola" con una carpeta enorme (miles de pistas) | MPD lo agrega en un comando; la cola crece y la página la pagina de a 100 (SPEC 11). Sin confirmación, como "+" a una lista en SPEC 10. |
| Tocar "Reproducir siguiente" varias veces seguidas invierte el orden (cada una queda justo después de la actual) | Comportamiento esperado de "siguiente" en reproductores; se documenta en el README. |
| Guardar con un nombre que coincide con otra lista por mayúsculas o tildes | MPD decide por el nombre de archivo exacto; `PlaylistName.EnsureValid` ya bloquea `/`, `\` y `.` inicial. |
| El menú queda abierto con una entrada vieja si la biblioteca cambia (`auto_update`) | MPD responde `ACK` si la `uri` ya no existe; la página muestra el error. |

## What is **not** in this spec

- Reproducir siguiente / agregar a la cola desde Listas.
- Sobrescribir una lista existente al guardar la cola.
- Arrastrar para reordenar.
- Cambios en ↑/↓/✕ y "Limpiar".
- Menú con clic derecho o pulsación larga.
- Actualización instantánea (MPD `idle` → SSE).
- OLED y navegación con botones.

Cada uno, si llega, va en su propia spec.
