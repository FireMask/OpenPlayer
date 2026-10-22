# SPEC 14 — Cola independiente de su origen

> **Status:** Approved
> **Depends on:** SPEC 03, SPEC 10, SPEC 11, SPEC 12, SPEC 13
> **Date:** 2026-10-22
> **Objective:** Activar el modo `consume` de MPD para que cada canción terminada o saltada salga de la cola (la actual queda arriba), reemplazar el nombre de "lista cargada" por una etiqueta de origen por fila que recuerda el Service, y hacer que ⏮ reinicie la canción actual.

## Scope

**In:**

- Mpd:
  - `consume 1` en cada comando que reproduce: `library.play` (`clear` + `consume 1` + `add` + `play 0`), `playlist.play` (`clear` + `consume 1` + `load` + `play N`) y `queue.play` (`consume 1` + `play N`).
  - `IQueue.EnableConsumeAsync()` (`consume 1`) y `IQueue.IdsAsync()` (`plchangesposid 0`: ids de la cola en orden).
  - ⏮ (`previous`): si en la Pi `previous` con `consume` no reinicia la actual, pasa a `seekcur 0`; vale para el botón físico y el de la web (mismo `button.pressed`).
- Service:
  - Al arrancar, `EnableConsumeAsync()`; si MPD no responde, registra un warning y sigue (el próximo play lo activa).
  - Quita `_loadedPlaylist`. Suma `_sources` (`Dictionary<int, string>`, id de MPD → origen) en memoria, bajo el lock global:
    - `playlist.play` → todas las pistas de la cola nueva = nombre de la lista.
    - `library.play` → la pista = "Biblioteca".
    - `queue.add` (al final o siguiente) → las pistas nuevas (ids después − ids antes) = "Biblioteca".
    - `queue.clear` → vacía el mapa; `IdsAsync` en cada agregado descarta ids que ya no están.
    - `playlist.rename`, `playlist.delete` y `queue.save` no cambian las etiquetas.
  - Se pierde al reiniciar el Service (las filas quedan sin etiqueta).
- Core: `queue.page` quita `playlist` y suma `source` (string o `null`) en cada entrada.
- Web agent (`index.html`):
  - Encabezado del panel: "Cola · N canciones" (sin "Lista: X").
  - Cada fila muestra su origen en el detalle ("artista · álbum · Favoritas"), si tiene.
  - Ya no recarga la cola tras renombrar o borrar una lista ni tras "Guardar como lista" por el nombre (sí por `queueVersion`).
- Pruebas: Core (serializador), Mpd (comandos exactos), Service (etiquetas en cada caso, arranque con MPD caído), web agent (sin cambios de rutas).
- Docs: `architecture.md` §5, §6, §7, §9; README (la cola consume lo escuchado; ⏮ reinicia).

**Out of scope (for future specs):**

- Historial real para ⏮: el Service recuerda lo escuchado y lo devuelve a la cola al ir hacia atrás (pedido del usuario, spec futura).
- Spotify-style: reproducir una lista sin borrar lo agregado con "Agregar a la cola" / "Reproducir siguiente".
- Interruptor de `consume` en la página o en `player.json`.
- Persistir las etiquetas de origen entre reinicios del Service.
- Actualizar etiquetas al renombrar o borrar una lista.
- Arrastrar para reordenar; agregar a la cola desde Listas.
- Actualización instantánea (MPD `idle` → SSE); OLED.

## Data model

**Core** (`src/OpenPlayer.Core/`):

```csharp
// Interfaces/IQueue.cs — dos métodos nuevos
Task EnableConsumeAsync(CancellationToken ct = default);           // consume 1
Task<IReadOnlyList<int>> IdsAsync(CancellationToken ct = default); // plchangesposid 0 → ids en orden de la cola
```

**`queue.page`** (`QueuePageMessage.Serialize(LibraryPage, IReadOnlyDictionary<int, string> sources)`): sin `playlist`; cada entrada suma `source` (`null` explícito si el id no tiene etiqueta).

```json
{"type":"queue.page","offset":0,"total":2,"entries":[{"uri":"A1.flac","id":17,"source":"Favoritas","title":"Rolling In The Deep","artist":"Adele","album":"21","durationSeconds":225},{"uri":"x.mp3","id":18,"source":null,"title":null,"artist":null,"album":null,"durationSeconds":null}]}
```

**MPD** (cambios de comandos):

| Llamada | Antes | Después |
|---|---|---|
| `MpdLibrary.PlayTrackAsync` | `clear`, `add`, `play 0` | `clear`, `consume 1`, `add`, `play 0` |
| `MpdPlaylistStore.PlayAsync` | `clear`, `load`, `play N` | `clear`, `consume 1`, `load`, `play N` |
| `MpdQueue.PlayAsync` | `play N` | `consume 1`, `play N` |
| `MpdQueue.EnableConsumeAsync` | — | `consume 1` |
| `MpdQueue.IdsAsync` | — | `plchangesposid 0` (pares `cpos`/`Id`) |
| `MpdPlayer.PreviousAsync` | `previous` | `seekcur 0`, solo si la prueba del paso 1 muestra que `previous` no reinicia la actual con `consume` |

**Service — etiquetas de origen** (`IpcServer._sources`, `Dictionary<int, string>`, en memoria, bajo `_commandLock`):

| Mensaje exitoso | Efecto |
|---|---|
| `playlist.play` | mapa = { cada id de `IdsAsync()` → nombre de la lista } |
| `library.play` | mapa = { cada id de `IdsAsync()` → `"Biblioteca"` } |
| `queue.add` | `IdsAsync()` antes y después; ids nuevos → `"Biblioteca"`; se descartan los ids que ya no están |
| `queue.clear` | mapa vacío |
| `playlist.rename`, `playlist.delete`, `queue.save`, `queue.remove`, `queue.move`, `queue.play` | sin cambio |
| Reinicio del Service | mapa vacío |

- Un mensaje que falla no cambia el mapa. Si la acción tuvo éxito pero `IdsAsync()` falla, se registra un warning, la respuesta sigue siendo `ok` y las pistas quedan sin etiqueta.
- Ids consumidos quedan en el mapa hasta el próximo `queue.add`, `queue.clear` o play que reemplace la cola (memoria acotada al tamaño de la cola).

**HTTP:** sin rutas nuevas ni cambios de contrato, salvo los campos de `queue.page`.

**Página:** sin datos nuevos. El encabezado ya no usa `page.playlist`; cada fila lee `entry.source`.

## Implementation plan

1. **Probar en la Pi (manual).**
   - `mpc consume on`, reproducir una lista de 3+ canciones, `mpc next` y luego `mpc prev`; anotar qué hace `previous` (reinicia la actual, detiene, otro).
   - Confirmar que al terminar o saltar una canción sale de la cola (`mpc playlist`).
   - El resultado decide si `MpdPlayer.PreviousAsync` cambia a `seekcur 0`; se anota en Decisiones.
2. **Mpd: `consume` y ids.**
   - `consume 1` en `PlayTrackAsync`, `MpdPlaylistStore.PlayAsync` y `MpdQueue.PlayAsync`.
   - `IQueue` suma `EnableConsumeAsync` e `IdsAsync`; `MpdQueue` los implementa; `FakeLibrary` los registra (ids configurables).
   - Pruebas con `FakeMpdServer`: comandos exactos de cada play; `consume 1`; `plchangesposid 0` devuelve los ids en orden.
3. **Mpd: ⏮.**
   - Según el paso 1: `MpdPlayer.PreviousAsync` envía `seekcur 0`, o queda igual.
   - Pruebas: comando exacto.
4. **Core: `queue.page` con `source`.**
   - `QueuePageMessage.Serialize(page, sources)`: quita `playlist`, suma `source` por entrada.
   - Pruebas: JSON exacto con etiqueta y con `null`.
5. **Service: etiquetas y arranque.**
   - Quita `_loadedPlaylist`; suma `_sources` según la tabla del modelo de datos.
   - `EnableConsumeAsync()` al arrancar; MPD caído → warning, sigue.
   - Pruebas con fakes: etiquetas tras `playlist.play`, `library.play`, `queue.add` (al final y siguiente), `queue.clear`; renombrar/borrar/guardar no las cambia; `queue.add` que falla no las cambia; `IdsAsync` que falla → `ok` sin etiqueta; arranque con MPD caído no falla. Se reemplazan las pruebas del nombre de lista de SPEC 11–13.
6. **`index.html`.**
   - Encabezado "Cola · N canciones"; detalle de la fila suma el origen.
   - Quitar las recargas por nombre (renombrar/borrar lista, "Guardar como lista"); el mensaje de guardado se mantiene.
7. **Docs.**
   - `architecture.md` §5 (panel), §6 (`IQueue`), §7 (`consume`, `queue.page.source`, etiquetas, ⏮), §9 (pendiente: historial de ⏮).
   - README: la cola consume lo escuchado; ⏮ reinicia; quitar la nota de "historial con `consume` apagado".
8. **Verificación en la Pi:** deploy, criterios de la sección siguiente desde PC y móvil.

Cada paso deja `dotnet test` y `pytest` en verde.

## Acceptance criteria

**Windows (automatizable):**

- [ ] `dotnet test`, `pytest tests/web-agent` y `pytest tests/hardware-agent` pasan.
- [ ] `MpdLibrary.PlayTrackAsync` envía `clear`, `consume 1`, `add`, `play 0`; `MpdPlaylistStore.PlayAsync` envía `clear`, `consume 1`, `load`, `play N`; `MpdQueue.PlayAsync(3)` envía `consume 1`, `play 3`.
- [ ] `MpdQueue.IdsAsync` sobre `plchangesposid 0` devuelve los ids en orden de la cola.
- [ ] `queue.page` produce exactamente el JSON del modelo de datos: sin `playlist`, con `source` (o `null`) en cada entrada.
- [ ] Tras `playlist.play` de "Viaje", todas las entradas de `queue.get` traen `"source":"Viaje"`; tras `library.play`, `"Biblioteca"`.
- [ ] Tras `playlist.play` de "Viaje" + `queue.add`, las pistas previas siguen con "Viaje" y la nueva trae "Biblioteca"; igual con `next`.
- [ ] `queue.clear` deja las entradas siguientes sin etiqueta; `playlist.rename`, `playlist.delete` y `queue.save` no cambian ninguna.
- [ ] Un `queue.add` que falla no cambia las etiquetas; si `IdsAsync` falla tras un agregado exitoso, la respuesta es `ok`.
- [ ] El Service arranca con MPD caído (registra el warning de `consume`) y responde `player.get_snapshot` con `error`.
- [ ] ⏮: `MpdPlayer.PreviousAsync` envía el comando decidido en el paso 1.

**Raspberry Pi (`deploy.ps1` y navegador en PC y móvil):**

- [ ] Tras reiniciar el Service, `mpc status` muestra `consume: on`.
- [ ] Reproducir "Favoritas" (N canciones) muestra "Cola · N canciones" con la primera resaltada arriba; cada fila dice "Favoritas" en el detalle.
- [ ] Al terminar una canción o pulsar ⏭ (web o botón físico), esa canción desaparece del panel y la siguiente queda arriba resaltada; el total baja en uno.
- [ ] ⏮ (web y botón físico) reinicia la canción actual desde 0:00 y la cola no cambia.
- [ ] "Agregar a la cola" de una pista de la Biblioteca la muestra al final con "Biblioteca"; las de "Favoritas" siguen con "Favoritas".
- [ ] Tocar una fila del medio salta a esa canción y las anteriores salen de la cola.
- [ ] Renombrar o borrar "Favoritas" no cambia las etiquetas de las filas.
- [ ] Reiniciar el Service deja las filas sin etiqueta y la cola igual.
- [ ] Al terminar la última canción, el panel muestra "Cola vacía".
- [ ] "Guardar como lista" guarda la actual y las siguientes, sin las ya escuchadas.

**Documentación:**

- [ ] `architecture.md` §5, §6, §7 y §9 describen `consume`, `IQueue.EnableConsumeAsync`/`IdsAsync`, `source` en `queue.page`, las etiquetas en memoria, ⏮ y el historial pendiente.
- [ ] README dice que la cola consume lo escuchado y que ⏮ reinicia la canción; ya no menciona el historial con `consume` apagado.

## Decisions

**Tomadas:**

- **Modo `consume` de MPD.** MPD ya quita la canción al terminar o saltarla; sin código que observe el fin de cada canción, y funciona igual con los botones físicos y `mpc`.
- **`consume 1` en cada play y al arrancar el Service.** Siempre activo, sin interruptor; si MPD se reinicia o alguien lo apaga con `mpc`, el próximo play lo vuelve a activar. Al arrancar con MPD caído solo se registra un warning.
- **⏮ reinicia la actual en esta spec.** Con `consume` no queda canción anterior en la cola; el comportamiento exacto de `previous` se mide en la Pi (paso 1) y, si no reinicia, se usa `seekcur 0`. Mismo comportamiento en web y botón físico (mismo `button.pressed`).
- **Resultado del paso 1 (MPD 0.24.4, `consume: on`):** `mpc next` quitó la canción saltada (`#1/7` → `#1/6`); `mpc prev` en 0:40 volvió a 0:00 de la misma canción sin quitarla (`#1/6`). `previous` ya reinicia la actual: `MpdPlayer.PreviousAsync` queda igual (`previous`) y no se usa `seekcur 0`.
- **Etiqueta de origen por fila, no "Lista: X".** La cola deja de estar atada a una lista: una cola mezclada (lista + agregados) muestra de dónde vino cada canción.
- **Etiquetas en memoria del Service, por id de MPD.** MPD no guarda metadatos propios por canción de la cola (`addtagid` solo sirve para canciones remotas); el id no cambia al mover ni consumir otras.
- **Ids nuevos por diferencia de `plchangesposid 0` antes y después.** `add` de una carpeta no devuelve los ids; la lista de posiciones/ids es liviana y sirve igual para pistas y carpetas.
- **Etiquetas como foto del momento.** Renombrar o borrar la lista no las cambia: es una pista de origen, no un vínculo. Quita la lógica de sincronizar nombres de SPEC 11.
- **"Guardar como lista" no cambia etiquetas.** El origen de cada canción sigue siendo el mismo.
- **Reproducir una lista o tocar una pista sigue reemplazando la cola.** El modelo tipo Spotify (mantener lo agregado) es otra spec.
- **`queue.page` sin `playlist`.** El único consumidor es la página; el campo queda reemplazado por `source` por entrada.

**Descartadas:**

- **El Service quita las canciones escuchadas.** Requiere observar MPD (`idle`) o sondear; `consume` lo hace nativo.
- **Interruptor de `consume` en la página o en `player.json`.** Pedido: siempre activo.
- **Historial real para ⏮ en esta spec.** Pedido del usuario como spec futura: el Service recuerda lo escuchado y lo reinserta.
- **Mantener el encabezado "Lista: X".** Con agregados y consumo, el nombre de una sola lista engaña.
- **Actualizar etiquetas al renombrar la lista.** Más lógica para una pista de origen.
- **Persistir etiquetas en disco.** Un reinicio del Service las borra; aceptado como pista no esencial.
- **`addtagid` de MPD.** Solo para canciones remotas.

## Risks

| Riesgo | Mitigación |
|---|---|
| `previous` con `consume` hace algo inesperado (detener, error) | Paso 1 lo mide en la Pi antes de escribir código; `seekcur 0` es la salida conocida. |
| Alguien apaga `consume` con `mpc` | El próximo play (web) lo vuelve a activar; mientras tanto la cola conserva lo escuchado. Aceptado. |
| Cola mezclada fuera de la web (`mpc add`) | Esas canciones quedan sin etiqueta (`source` `null`); la fila solo muestra artista y álbum. |
| `IdsAsync` falla justo después de un agregado exitoso | Respuesta `ok`, warning en el log, las nuevas quedan sin etiqueta. |
| Cola muy grande: `plchangesposid 0` antes y después de cada agregado | Respuesta liviana (2 líneas por canción); bajo el lock global y solo al agregar. |
| La cola se recarga en la página al terminar cada canción (`queueVersion` cambia) | Una recarga por canción; mismo costo que cualquier otro cambio de la cola (SPEC 11). |
| Usuarios acostumbrados a ⏮ para volver a la canción anterior | Documentado en README; el historial real queda como spec futura. |
| `consume` encendido al usar `mpc` para otras cosas fuera del reproductor | Es el mismo MPD del reproductor; documentado en README. |

## What is **not** in this spec

- Historial real para ⏮ (spec futura, pedido del usuario).
- Reproducir una lista sin borrar lo agregado (modelo tipo Spotify).
- Interruptor de `consume`.
- Persistir o actualizar las etiquetas de origen.
- Arrastrar para reordenar; agregar a la cola desde Listas.
- Actualización instantánea (MPD `idle` → SSE); OLED.

Cada uno, si llega, va en su propia spec.
