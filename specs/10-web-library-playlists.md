# SPEC 10 — Biblioteca y playlists desde la web

> **Status:** Implemented
> **Depends on:** SPEC 02, SPEC 03, SPEC 07, SPEC 08, SPEC 09
> **Date:** 2026-10-21
> **Objective:** Agregar a la página del web agent una pestaña de biblioteca (carpetas + búsqueda, paginada) y otra de playlists guardadas de MPD (crear, renombrar, borrar, agregar pista o carpeta, quitar, reordenar, reproducir), sobre nuevos mensajes IPC con respuesta que el Service ejecuta mediante `ILibrary` e `IPlaylistStore`.

## Scope

**In:**

- Core:
  - Modelos `LibraryEntry` y `LibraryPage`; contratos `ILibrary` e `IPlaylistStore` (`src/OpenPlayer.Core/Interfaces/`).
  - `PlaylistName.EnsureValid`: 1–100 caracteres, sin `/`, `\`, salto de línea ni `.` inicial.
  - Mensajes IPC nuevos en `IpcMessage.cs` y su parseo en `IpcMessageParser`; respuestas `ok`, `library.page`, `playlist.list` y el `error` existente.
- Mpd:
  - Escape de argumentos en `MpdClient` (comillas dobles, `\` y `"` escapados).
  - `MpdLibrary` (`lsinfo`, `search any`) y `MpdPlaylistStore` (`listplaylists`, `listplaylistinfo`, `playlistclear`, `playlistadd`, `playlistdelete`, `playlistmove`, `rename`, `rm`), y reproducir (`clear` + `load`/`add` + `play N`).
- Service: `IpcServer` atiende los mensajes nuevos bajo el mismo lock y responde una línea por pedido.
- Web agent:
  - `ipc.py`: un método por mensaje nuevo; límite de respuesta 1 MB.
  - `server.py`: rutas `/api/library…` y `/api/playlists…`.
  - `index.html`: pestañas Reproductor / Biblioteca / Listas; navegación por carpetas con migas, búsqueda, paginado de 100; crear/renombrar/borrar (con confirmación) listas; agregar pista o carpeta a una lista; quitar; ↑/↓ para reordenar; reproducir lista desde el inicio o desde una pista; reproducir pista de la biblioteca.
- Pruebas: Core (parser, nombres), Mpd (escape y comandos con `FakeMpdServer`), Service, web agent (ipc + HTTP).
- Docs: `architecture.md` §5, §6, §7 y §9; README; en SPEC 09 cambiar "SPEC 10" por "spec futura".

**Out of scope (for future specs):**

- OLED y navegación con botones (`menu`, volumen como flechas) — spec futura.
- Ver o editar la cola en vivo (más allá de reemplazarla al reproducir).
- Navegación artista → álbum → pista (`list`).
- Botón de reescaneo (`auto_update` de SPEC 07 lo cubre).
- Autenticación y HTTPS.
- Arrastrar y soltar para reordenar.
- Carátulas.
- Actualización instantánea (MPD `idle` → SSE).
- Base SQLite propia, historial o ratings.

## Data model

**Core** (`src/OpenPlayer.Core/`):

```csharp
// Models/LibraryEntry.cs — Track null ⇔ carpeta
public sealed record LibraryEntry(string Uri, Track? Track);

// Models/LibraryPage.cs — una página de 100; en playlists, posición = Offset + índice
public sealed record LibraryPage(int Offset, int Total, IReadOnlyList<LibraryEntry> Entries);

// Interfaces/ILibrary.cs
Task<LibraryPage> BrowseAsync(string path, int offset, CancellationToken ct = default);   // lsinfo; "" = raíz
Task<LibraryPage> SearchAsync(string query, int offset, CancellationToken ct = default);  // search any
Task PlayTrackAsync(string uri, CancellationToken ct = default);                          // clear + add + play

// Interfaces/IPlaylistStore.cs
Task<IReadOnlyList<string>> ListAsync(CancellationToken ct = default);
Task<LibraryPage> GetAsync(string name, int offset, CancellationToken ct = default);      // listplaylistinfo
Task CreateAsync(string name, CancellationToken ct = default);                            // existe → error; playlistadd "" + playlistclear
Task RenameAsync(string name, string newName, CancellationToken ct = default);
Task DeleteAsync(string name, CancellationToken ct = default);                            // rm
Task AddAsync(string name, string uri, CancellationToken ct = default);                   // pista o carpeta (recursivo)
Task RemoveAsync(string name, int position, CancellationToken ct = default);              // playlistdelete
Task MoveAsync(string name, int from, int to, CancellationToken ct = default);            // playlistmove
Task PlayAsync(string name, int position, CancellationToken ct = default);                // clear + load + play N
```

- Carpetas primero, luego pistas, en el orden de MPD; las entradas `playlist:` de `lsinfo` se ignoran.
- El Service pagina sobre la respuesta completa de MPD (`PageSize = 100`).

**Validación (Core, al parsear):**

| Campo | Regla |
|---|---|
| `name`, `newName` | `PlaylistName.EnsureValid`: 1–100 caracteres, sin `/`, `\`, `\n`, `\r` ni `.` inicial |
| `uri` | 1–1024 caracteres, sin caracteres de control |
| `path` | 0–1024 caracteres, sin caracteres de control (`""` = raíz) |
| `query` | 2–100 caracteres |
| `offset`, `position`, `from`, `to` | entero JSON ≥ 0; `offset` y `position` opcionales (0) |

Inválido → `error` con el `request` y la conexión sigue.

**Mensajes IPC nuevos** (`architecture.md` §7; todos responden una línea):

```json
{"type":"library.browse","path":"Rock/AC DC","offset":0}
{"type":"library.search","query":"thunder","offset":0}
{"type":"library.play","uri":"Rock/AC DC/01.flac"}
{"type":"playlist.list"}
{"type":"playlist.get","name":"Viaje","offset":0}
{"type":"playlist.create","name":"Viaje"}
{"type":"playlist.rename","name":"Viaje","newName":"Viaje 2026"}
{"type":"playlist.delete","name":"Viaje"}
{"type":"playlist.add","name":"Viaje","uri":"Rock/AC DC"}
{"type":"playlist.remove","name":"Viaje","position":3}
{"type":"playlist.move","name":"Viaje","from":3,"to":2}
{"type":"playlist.play","name":"Viaje","position":0}
```

Respuestas:

```json
{"type":"ok","request":"playlist.add"}
{"type":"library.page","offset":0,"total":2,"entries":[{"uri":"Rock/AC DC","directory":true},{"uri":"Rock/x.mp3","directory":false,"title":"X","artist":"A","album":null,"durationSeconds":210}]}
{"type":"playlist.list","playlists":["Viaje","Gym"]}
{"type":"error","request":"playlist.create","message":"Playlist 'Viaje' already exists"}
```

- `library.browse`, `library.search` y `playlist.get` responden `library.page`.
- Las mutaciones y `*.play` responden `ok`.
- `null` explícitos, como en `player.snapshot`.
- Un `ACK` de MPD (no existe, posición fuera de rango) o MPD caído → `error` con el mensaje de MPD.

**MPD (`MpdClient`):** todo argumento de texto va entre comillas dobles, con `\` → `\\` y `"` → `\"`. Los números se formatean con `InvariantCulture`.

**HTTP** (web agent; `<name>` y `<pos>` en la ruta URL-encoded; cuerpos JSON ≤ 4 KB):

| Método y ruta | IPC | Éxito |
|---|---|---|
| `GET /api/library?path=&offset=` | `library.browse` | `200` `library.page` |
| `GET /api/library/search?q=&offset=` | `library.search` | `200` `library.page` |
| `POST /api/library/play` `{"uri"}` | `library.play` | `204` |
| `GET /api/playlists` | `playlist.list` | `200` |
| `POST /api/playlists` `{"name"}` | `playlist.create` | `204` |
| `GET /api/playlists/<name>?offset=` | `playlist.get` | `200` `library.page` |
| `POST /api/playlists/<name>/rename` `{"newName"}` | `playlist.rename` | `204` |
| `DELETE /api/playlists/<name>` | `playlist.delete` | `204` |
| `POST /api/playlists/<name>/tracks` `{"uri"}` | `playlist.add` | `204` |
| `DELETE /api/playlists/<name>/tracks/<pos>` | `playlist.remove` | `204` |
| `POST /api/playlists/<name>/move` `{"from","to"}` | `playlist.move` | `204` |
| `POST /api/playlists/<name>/play` `{"position"}` opcional | `playlist.play` | `204` |

Errores comunes a todas:

- `400`: cuerpo o query inválido según la tabla de validación (el web agent valida la forma; el Core vuelve a validar).
- `502`: el Service responde `error`; el cuerpo es esa línea, para que la página muestre `message`.
- `503`: Service inalcanzable o sin respuesta en 5 s.
- `403`, `404` y `405`: como en SPEC 08.

## Implementation plan

1. **Escape en `MpdClient`.**
   - Helper `MpdClient.Quote(string)` (`"` y `\` escapados).
   - Pruebas: comillas, barra invertida, espacios, UTF-8, y una línea exacta enviada a `FakeMpdServer`.
   - Sin cambiar los comandos existentes.
2. **Core: modelos, contratos y validación.**
   - `LibraryEntry`, `LibraryPage`, `ILibrary`, `IPlaylistStore`, `PlaylistName.EnsureValid`.
   - Pruebas de nombres válidos e inválidos (vacío, 101 caracteres, `/`, `\`, `\n`, `.x`).
3. **Core: mensajes.**
   - Records de los 12 mensajes en `IpcMessage.cs` y su parseo en `IpcMessageParser`.
   - Serializadores `OkMessage`, `LibraryPageMessage`, `PlaylistListMessage` (como `SnapshotMessage`).
   - Pruebas: cada mensaje válido; campos faltantes o de tipo incorrecto; `offset` opcional = 0; `null` explícitos.
4. **Mpd: `MpdLibrary`.**
   - `BrowseAsync` (`lsinfo`, paginado, sin `playlist:`), `SearchAsync` (`search any`), `PlayTrackAsync` (`clear`, `add`, `play` en una sola conexión).
   - Pruebas con `FakeMpdServer`: carpetas antes que pistas, `offset`/`total`, metadatos faltantes, `ACK`.
5. **Mpd: `MpdPlaylistStore`.**
   - Los 9 métodos.
   - `CreateAsync` consulta `listplaylists` y, si el nombre existe, lanza `MpdException` sin tocar MPD.
   - Pruebas: comando exacto por método, paginado de `listplaylistinfo`, duplicado, `ACK` de no existe.
6. **Service.**
   - `IpcServer` despacha los mensajes nuevos bajo `_commandLock` y responde `ok` / página / `error`.
   - `Program.cs` registra `MpdLibrary` y `MpdPlaylistStore`.
   - Pruebas con fakes: cada mensaje llama al método correcto; una excepción → `error` con `request`, y la conexión sigue.
7. **Web agent `ipc.py`.**
   - `request(message)` genérico que devuelve la línea de respuesta (timeout 5 s, máx. 1 MB) y un método fino por mensaje.
   - `snapshot()` sigue igual.
   - Pruebas con el servidor TCP falso: línea exacta enviada y respuesta devuelta.
8. **Web agent `server.py`.**
   - Rutas de la tabla HTTP, validación de query y cuerpo (≤ 4 KB), mapeo `ok` → `204` y `error` → `502`.
   - Pruebas HTTP: cada ruta con éxito, cada `400`, `502`, `503`, `405` y nombre URL-encoded con espacios y `%`.
9. **`index.html`: pestañas y Biblioteca.**
   - Pestañas Reproductor / Biblioteca / Listas; la de Reproductor no cambia.
   - Carpetas con migas, búsqueda, "Más" para la siguiente página.
   - Tocar una pista la reproduce; botón "+" abre el selector de lista (pista o carpeta).
10. **`index.html`: Listas.**
    - Lista de listas; crear y renombrar con `prompt`, borrar con `confirm`.
    - Abrir una lista: pistas con ↑/↓/✕, "Reproducir" desde el inicio o tocando una pista.
    - Errores: se muestra el `message` del `502` y "Sin conexión con el reproductor" en `503`.
11. **Docs.**
    - `architecture.md` §5 (contrato HTTP), §6 (`ILibrary`, `IPlaylistStore`), §7 (mensajes) y §9 (marcar lo implementado).
    - README.
    - SPEC 09: "SPEC 10" → "spec futura".
12. **Verificación en la Pi:** deploy, criterios de la sección siguiente desde PC y móvil.

Cada paso deja `dotnet test` y `pytest` en verde. Los pasos 1–6 no agregan nada a la web, pero los mensajes nuevos ya se pueden probar con `socat`.

## Acceptance criteria

**Windows (automatizable):**

- [x] `dotnet test`, `pytest tests/web-agent` y `pytest tests/hardware-agent` pasan.
- [x] `MpdClient.Quote` convierte `a "b" \c` en `"a \"b\" \\c"`; un nombre con espacios y tildes llega a `FakeMpdServer` como un solo argumento.
- [x] `PlaylistName.EnsureValid` acepta `Viaje 2026` y `Ñandú` y rechaza `""`, 101 caracteres, `a/b`, `a\b`, `a\nb` y `.x`.
- [x] `IpcMessageParser` devuelve el record correcto para cada uno de los 12 mensajes; sin `offset`/`position` usa 0; `name` faltante, `offset` `-1`, `"3"` o `3.5`, `query` de 1 carácter y `uri` vacío son inválidos sin lanzar.
- [x] Un mensaje inválido de los nuevos responde `error` con su `request` y la conexión procesa el siguiente.
- [x] `BrowseAsync("", 0)` sobre 3 carpetas y 150 pistas devuelve `total` 153, 100 entradas con las 3 carpetas primero; `offset` 100 devuelve las 53 restantes; las entradas `playlist:` no aparecen.
- [x] `PlayTrackAsync` envía `clear`, `add "<uri>"` y `play 0` en ese orden en una conexión; `PlayAsync("Viaje", 4)` envía `clear`, `load "Viaje"` y `play 4`.
- [x] `CreateAsync` con un nombre existente lanza sin tocar la lista; con uno nuevo envía `playlistadd "<name>" ""` y `playlistclear "<name>"` en una conexión.
- [x] `AddAsync`, `RemoveAsync`, `MoveAsync`, `RenameAsync` y `DeleteAsync` envían `playlistadd`, `playlistdelete`, `playlistmove`, `rename` y `rm` con los argumentos citados.
- [x] Un `ACK` de MPD en cualquier operación llega al cliente IPC como `error` con el mensaje de MPD, y el Service sigue corriendo.
- [x] Cada fila de la tabla HTTP devuelve su código de éxito con el IPC esperado; cuerpo > 4 KB, JSON inválido o campo inválido → `400`; Service `error` → `502` con la línea como cuerpo; Service caído → `503`; método incorrecto → `405`; cliente fuera de rango → `403`.
- [x] `GET /api/playlists/Mi%20lista%20100%25` llega como `playlist.get` con `name` `Mi lista 100%`.
- [x] El web agent sigue usando solo stdlib.

**Raspberry Pi (`deploy.ps1` y navegador en PC y móvil):**

- [x] La pestaña Biblioteca muestra la raíz de `/home/andres/Music`; entrar a una carpeta y volver con las migas funciona; con más de 100 entradas aparece "Más" y carga el resto.
- [x] Buscar un texto de un título conocido lo muestra en 3 s o menos.
- [x] Tocar una pista de la biblioteca reemplaza la cola y `mpc status` muestra esa pista reproduciendo.
- [x] Crear "Prueba", agregar 2 pistas y una carpeta: `mpc playlist Prueba` lista esas pistas en ese orden, con la carpeta expandida.
- [x] ↑ sobre la segunda pista la deja primera en `mpc playlist Prueba`; ✕ la quita.
- [x] Renombrar "Prueba" a "Prueba 2" se refleja en `mpc lsplaylists`; crear "Prueba 2" otra vez muestra el mensaje de error en la página.
- [x] Borrar pide confirmación; al cancelar no cambia nada; al aceptar desaparece de `mpc lsplaylists` y ningún archivo de música se borra.
- [x] "Reproducir" de una lista y tocar su tercera pista dejan `mpc status` en la pista 1 y la 3 de la cola, respectivamente.
- [x] Un nombre con espacios, tildes y `"` funciona en crear, abrir, agregar y borrar.
- [x] Con el Service detenido, cualquier acción de Biblioteca o Listas muestra "Sin conexión con el reproductor"; al reiniciarlo vuelve a funcionar sin recargar.
- [x] La pestaña Reproductor (botones, estado, barra de SPEC 09) funciona como antes.

**Documentación:**

- [x] `architecture.md` §5, §6, §7 y §9 describen contrato HTTP, contratos, mensajes y lo implementado.
- [x] README menciona las pestañas Biblioteca y Listas.
- [x] SPEC 09 ya no reserva "SPEC 10".

## Decisions

**Tomadas:**

- **Separar web (SPEC 10) y OLED + botones (spec futura).** El OLED depende de la fase 8 (hardware sin montar) y toca otro agente; esta spec deja listos los mensajes IPC que esa spec reutilizará.
- **Playlists guardadas de MPD (`.m3u` en `playlist_directory`).** La arquitectura delega en MPD; sin segunda copia que sincronizar, y `mpc` sigue viendo las mismas listas.
- **La web pasa por el Service, nunca habla con MPD.** Consistente con SPEC 08: un solo lock, una sola validación, y el futuro OLED usa el mismo camino.
- **Los mensajes nuevos responden (`ok` / `error`).** La edición necesita informar duplicados o listas inexistentes; `button.pressed` y `player.seek` siguen sin respuesta.
- **Navegación por carpetas + búsqueda.** Coincide con cómo se copia la música por Samba (SPEC 07); no depende de etiquetas bien puestas.
- **Paginado de 100 en el Service, sin tope de búsqueda.** `lsinfo` y `search` no paginan en MPD 0.23; cortar en el Service mantiene las respuestas IPC chicas (~30 KB). Una sola regla para biblioteca, búsqueda y playlists.
- **Reproducir reemplaza la cola (`clear` + `load`/`add` + `play N`).** Sin UI de cola en esta spec; el comportamiento es predecible.
- **Crear con `playlistadd "<nombre>" ""` + `playlistclear`, verificando antes con `listplaylists`.** MPD no tiene "crear vacía"; `save` copiaría la cola actual. Hallado en la Pi (MPD 0.23): `playlistclear` de un nombre inexistente responde `No such playlist` en vez de crear el `.m3u`. Agregar la raíz crea el archivo y `playlistclear` lo vacía, en una conexión; la UI no cambia. Se descartó "agregar una pista cualquiera + `playlistdelete 0`": obtener una pista barata exige filtros de `find`/`search` dependientes de versión. Con una biblioteca vacía, crear falla con el mensaje de MPD.
- **`~/Playlists` con dueño `mpd` (`chown mpd:andres`, `chmod 2775`).** Hallado en la Pi: MPD corre como `mpd` y no podía escribir en la carpeta de `andres` (`Permission denied`). Documentado en `assembly.md`; faltaba desde SPEC 07.
- **Escape de argumentos en `MpdClient`.** Nombres y URIs son entrada de usuario; hasta ahora solo se enviaban números.
- **Validación en Core y forma en el web agent.** El Core es la autoridad (también para la spec de OLED + botones); el web agent rechaza temprano con `400`.
- **Agregar pista o carpeta.** `playlistadd` con una carpeta la expande recursivamente sin código propio.
- **↑/↓ para reordenar.** Funciona en táctil y teclado; el arrastrar y soltar HTML5 nativo no funciona en móvil.
- **`prompt`/`confirm` nativos.** Sin diálogos propios; confirmación solo al borrar.
- **Sin autenticación.** Borrar una lista solo elimina el `.m3u`, nunca música; solo LAN (revisión de SPEC 08).
- **`error` del Service → `502`, timeout IPC de 5 s.** Igual que `/api/snapshot`; 5 s porque `lsinfo`/`search` sobre miles de pistas en la Zero 2 W pueden tardar.
- **Sin botón de reescaneo.** `auto_update` (SPEC 07) ya indexa lo copiado por Samba.

**Descartadas:**

- **OLED y web en una spec.** Demasiadas áreas y decisiones; ver arriba.
- **Playlists en JSON propio.** Duplicaría datos que MPD ya maneja e invisible para `mpc`.
- **Web agent hablando con MPD.** Rompe la regla de SPEC 08 y duplicaría validación y lock.
- **Árbol artista → álbum → pista.** Depende de etiquetas; spec futura si hace falta.
- **Lista plana de toda la biblioteca.** Inmanejable con miles de pistas.
- **Tope de 200 resultados en la búsqueda.** El paginado ya acota la respuesta; una regla menos.
- **`PlaylistInfo`.** MPD solo da nombre y fecha; una lista de `string` basta.
- **Editar la cola en vivo.** Otra UI y otro conjunto de mensajes; spec futura.
- **Arrastrar y soltar.** No funciona en táctil sin una librería.

## Risks

| Riesgo | Mitigación |
|---|---|
| `lsinfo` de la raíz o `search` sobre miles de pistas supera `mpd.connectTimeoutMs` (un solo timeout por operación en `MpdClient`) | Medir en la Pi con la biblioteca real; si pasa, subir `mpd.connectTimeoutMs` en `player.json`. Navegar por carpetas mantiene cada `lsinfo` chico. |
| Una consulta larga retiene `_commandLock` y retrasa los botones físicos | Aceptado: las consultas pagan solo al navegar. Si molesta, lock separado para lecturas en otra spec. |
| `playlistclear` sobre un nombre inexistente no crea el `.m3u` en la versión de MPD de la Pi | **Ocurrió** (MPD 0.23: `No such playlist`). Se crea con `playlistadd` de la raíz + `playlistclear` (ver Decisiones). Con decenas de miles de pistas, ese `playlistadd` escribe un `.m3u` grande una vez antes de vaciarlo; si pesa, cambiar a una sola pista. |
| Paginado inconsistente si la biblioteca o la lista cambia entre dos páginas (`auto_update`, otra pestaña) | Aceptado: "Más" puede repetir o saltar entradas; recargar la carpeta lo corrige. |
| Reordenar o quitar con posiciones viejas (otra pestaña o `mpc` cambió la lista) | MPD responde `ACK` si la posición no existe; si existe, mueve otra pista. La página recarga la lista después de cada operación. |
| "Reproducir" borra la cola actual sin aviso | Aceptado y documentado en README; no hay UI de cola que perder. |
| Cualquiera en la LAN puede borrar o editar listas | Aceptado: solo `.m3u`, nunca música; respaldo por Samba si se quiere. |
| `"`, `\` o UTF-8 en nombres rompen el comando MPD | `MpdClient.Quote` con pruebas; criterio de aceptación en la Pi con `"` y tildes. |

## What is **not** in this spec

- OLED y navegación con botones — spec futura.
- Ver o editar la cola en vivo.
- Navegación artista → álbum → pista.
- Botón de reescaneo.
- Autenticación y HTTPS.
- Arrastrar y soltar.
- Carátulas.
- Actualización instantánea (MPD `idle` → SSE).
- SQLite propia, historial o ratings.

Cada uno, si llega, va en su propia spec.
