# Architecture — OpenPlayer

**Estado:** diseño inicial v1.0; algunas decisiones deben validarse en el dispositivo real.

## 1. Propósito

OpenPlayer es un reproductor de música local modular para Raspberry Pi Zero 2 W. Debe funcionar sin monitor ni teclado después de configurarse. La primera versión prioriza audio fiable, controles físicos y administración por SSH. La pantalla redonda (SPEC 17) es opcional; Bluetooth como salida y batería integrada son fases posteriores.

## 2. Hardware conocido y objetivos

- Raspberry Pi Zero 2 W.
- microSD de 32 GB.
- DAC USB existente con jack de 3.5 mm.
- Protoboard, cables Dupont y botones momentáneos.
- Impresora 3D para la carcasa.
- Pantalla redonda IPS de 1,28" 240x240 con controlador GC9A01 (módulo "1.28 TFT ver 1.0", 7 pines, sin BL), por SPI, opcional (SPEC 17).
- Bluetooth integrado de la Pi; objetivo: salida a auriculares mediante A2DP.
- Alimentación portátil futura. Durante el desarrollo inicial, usar fuente USB estable o power bank validado.

No se ha confirmado el modelo exacto del DAC, la distribución de Raspberry Pi OS, el modelo de batería ni el circuito de carga. Descubrir y documentar esos datos antes de cerrar configuraciones específicas.

## 3. Principios arquitectónicos

1. **Separación por capas:** dominio y contratos no dependen de hardware ni de MPD.
2. **MPD como motor de reproducción:** no desarrollar decodificadores propios en la primera versión.
3. **Una sola fuente de verdad:** MPD es autoridad para canción, cola, estado, posición y volumen cuando este último lo controla MPD.
4. **C# como orquestador:** valida comandos/eventos, coordina adaptadores y publica el estado.
5. **Python como agente de hardware:** lee GPIO, aplica debounce y emite eventos; también dibuja la pantalla a partir del estado que publica el Service (SPEC 17).
6. **Interfaces reemplazables:** el hardware no invoca MPD directamente.
7. **Seguridad local:** MPD y IPC solo deben estar disponibles para procesos locales o usuarios/grupos autorizados.
8. **Resiliencia:** los servicios se reinician ante fallos, reconectan y registran errores sin bucles de log descontrolados.

## 4. Diagrama lógico

```text
[Botones GPIO] ---> [Hardware Agent: Python] -- JSON Lines / Unix socket --+
[Pantalla GC9A01] <-- SPI -- (Hardware Agent, player.subscribe)          |
                                                                         |
[SSH: mpc / diagnóstico] -----------------------------------------------+--> [OpenPlayer.Service: C#]
                                                                         |       |
[Navegador en la LAN] -- HTTP :8080 --> [Web Agent: Python] -------------+       +--> [OpenPlayer.Core]
                                                                                 |
                                                                                 +--> [OpenPlayer.Mpd] --> [MPD]
                                                                                                      |
                                                                                          [ALSA / PipeWire]
                                                                                           /           \
                                                                                     [DAC USB]    [Bluetooth A2DP]
```

SSH es un canal de administración; no implica que la aplicación deba aceptar comandos shell desde la red. El web agent (SPEC 08) es otra entrada como el hardware agent: traduce HTTP a mensajes IPC y nunca habla con MPD.

## 5. Componentes y responsabilidades

### `OpenPlayer.Core`

Biblioteca .NET sin dependencias de plataforma ni paquetes MPD. Contiene:

- Modelos: `Track`, `Playlist`, `PlaybackSnapshot`, `PlayerSettings`.
- Contratos: `IPlayer`, `ILibrary`, `IPlaylistStore`, `IQueue`, `IAudioOutputSelector` (este último puede esperar a la fase Bluetooth).
- Comandos de dominio o servicios de aplicación: play/pause, next, previous, volumen y selección de pista.
- Validación de parámetros y reglas de estado que no dependan del motor.

No debe abrir sockets, leer GPIO, llamar procesos externos ni acceder a archivos de configuración directamente.

### `OpenPlayer.Mpd`

Adaptador que encapsula el protocolo MPD:

- Conexión por defecto a `127.0.0.1:6600`.
- Comandos de reproducción y navegación.
- Consultas de estado y canción actual.
- Búsqueda/listado de biblioteca y manejo de playlists guardadas en MPD.
- Reconexión con backoff y manejo de respuestas de error.

Preferir un cliente MPD .NET mantenido si es compatible con el runtime y el protocolo. Si se implementa un cliente mínimo propio, tratar correctamente el saludo, el token de versión, la terminación de respuestas, `OK`, `ACK`, el escape de argumentos y los comandos listados. No construir comandos concatenando entrada de usuario sin escape.

### `OpenPlayer.Service`

Proceso principal C#/.NET:

- Crea dependencias y carga configuración.
- Recibe eventos del Hardware Agent por socket Unix.
- Valida mensajes y traduce botones a comandos de aplicación.
- Coordina el adaptador MPD.
- Expone estado normalizado para futuras interfaces.
- Escribe logs estructurados y maneja cancelación/apagado.
- No expone HTTP: la web vive en el web agent (SPEC 08), que usa el mismo socket.

### `src/hardware-agent`

Proceso Python:

- Configura botones GPIO con pull-up y debounce.
- Envía eventos JSON Lines al socket Unix.
- Maneja reconexión si el servicio aún no está disponible.
- Dibuja la pantalla con el estado de `player.subscribe` (SPEC 17); no consulta MPD directamente.
- Debe permitir simulación o pruebas sin hardware real.

Implementado en SPEC 05 (Python 3, solo stdlib y `gpiozero` con `lgpio`, paquetes del sistema, sin venv):

- `config.py`: lee `hardware.buttons`, `hardware.debounceSeconds` e `ipc.unixSocketPath` de `player.json`; config inválida → exit 1 nombrando el campo.
- `buttons.py`: un `gpiozero.Button` por pin (pull-up, `bounce_time` = debounce, aplicado por `lgpio`); el callback solo encola.
- `sender.py`: hilo que envía `button.pressed` con `sequence` por proceso. Reconexión con espera incremental 0.5–10 s; registra solo `connected`/`disconnected`; detecta el cierre del Service en reposo (`select`). Sin conexión, la pulsación se descarta (no se reenvía).
- `main.py`: entrada; SIGTERM/Ctrl+C → exit 0.

Pantalla (SPEC 17, `python3-pil`, `python3-spidev` y `fonts-dejavu-core`; solo con `hardware.display.enabled`):

- `config.py`: `hardware.display` opcional (ausente o `enabled: false` → sin pantalla; DC/RST no pueden repetir pines de botones).
- `gc9a01.py`: driver mínimo; init de referencia (Waveshare), cuadro completo 240x240 RGB565 por SPI, DC/RST con `gpiozero`, rotación con Pillow.
- `screen.py`: `render(View)` → imagen: título, artista, ícono, anillo de progreso y volumen; "Detenido", "Sin conexión", "MPD no responde". Texto cortado con "…" al ancho del círculo.
- `display.py`: hilo con su propia conexión `player.subscribe`, reintento cada 2 s; avanza la posición localmente una vez por segundo en `playing` y redibuja solo si cambia la vista.
- Un fallo de la pantalla (paquete, SPI, init) registra `display init failed` y los botones siguen.
- Unidad `deploy/openplayer-hardware.service` (usuario `openplayer`, grupos `gpio` y `spi`), instalada por `deploy/install.sh`. Pruebas en `tests/hardware-agent` con `MockFactory` y un servidor TCP local.

### `src/web-agent`

Proceso Python (SPEC 08, solo stdlib): página con los 6 botones y el estado, para controlar el reproductor desde un navegador de la red local sin GPIO.

- `config.py`: lee `ipc.unixSocketPath` y `web.port` (1024–65535) de `player.json`; ignora `hardware`. Config inválida → exit 1 nombrando el campo.
- `ipc.py`: una conexión al socket por pedido HTTP; `button.pressed` sin `sequence`; `player.get_snapshot` con timeout de 2 s; `player.seek` (SPEC 09). Biblioteca, playlists (SPEC 10) y cola (SPEC 11 a 13) con `request()`: timeout de 5 s y respuesta de hasta 1 MB. `subscribe()` (SPEC 16): conexión dedicada con `player.subscribe`, genera cada línea a medida que llega, sin timeout de lectura; `IpcUnavailable` si no conecta o se corta.
- `server.py`: `ThreadingHTTPServer` en `::` (IPv4 e IPv6). Solo acepta clientes de `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `::1` y `fe80::/10` (IPv4 mapeadas se evalúan como IPv4); el resto recibe `403`. Sin autenticación ni HTTPS. `Events` (SPEC 16): un hilo mantiene la suscripción IPC mientras corre el web agent, guarda la última línea y la reparte a una `queue.Queue(maxsize=16)` por página de `/api/events` (cola llena → la página se descarta); si el Service se cae, reparte la línea `error` de `player.get_snapshot` y reintenta cada 2 s.
- `index.html`: botones y línea de estado; título y artista se insertan como texto, nunca como HTML. Actualización instantánea (SPEC 16): `EventSource("/api/events")`, cada mensaje se procesa igual que `/api/snapshot`; mientras el stream está conectado no hay sondeo, y al caer (`onerror`, o `503` por el tope) vuelve el sondeo de 2 s hasta que el navegador reconecte. Barra de progreso (`<input type="range">` + `m:ss / m:ss`, SPEC 09): avanza localmente entre snapshots si `playing`, el sondeo no la mueve mientras se arrastra, al soltar envía `POST /api/seek`; oculta sin `durationSeconds`, deshabilitada en `stopped`.
- Pestañas Reproductor / Biblioteca / Listas (SPEC 10). Biblioteca: carpetas con migas, búsqueda (≥ 2 caracteres), "Más" cada 100; tocar una pista reemplaza la cola y la reproduce; "+" abre un menú (`<dialog>`, SPEC 13) con el nombre de la entrada: "Reproducir siguiente" (después de la actual), "Agregar a la cola" (al final) y "Agregar a una lista ›", que cambia el contenido del mismo diálogo por las listas y "‹ Atrás"; vale para pistas, carpetas y resultados de búsqueda. Listas: crear/renombrar con `prompt`, borrar con `confirm`; abrir una lista: ↑/↓/✕ y reproducir desde el inicio o desde una pista. Tras cada cambio, y cada vez que se vuelve a la pestaña Listas (SPEC 11: refleja lo agregado desde Biblioteca), la lista abierta o el índice se recarga para no usar posiciones viejas.
- Panel "Cola" (SPEC 11): a la derecha en todas las pestañas con ventana ≥ 900 px; más angosta, debajo de los controles solo en Reproductor. Encabezado "Cola · N canciones" (SPEC 14; antes "Lista: <nombre>"); filas con número, título (o nombre de archivo), "artista · álbum · origen" (origen = `source`, SPEC 14, si tiene) y m:ss. Con `consume` (SPEC 14) la actual está siempre primera: lo escuchado o saltado sale de la cola. La cola se pide solo cuando el snapshot trae otro `queueVersion` (o al recuperar la conexión): páginas desde 0 hasta incluir `queuePosition`, luego "Más". En cada snapshot se mueve el resaltado de la actual (color + 3 barras CSS: animadas en `playing`, congeladas en `paused`, ocultas en `stopped`, quietas con `prefers-reduced-motion`) y se centra si no está visible, salvo 10 s después de que el usuario desplace el panel. Tocar una fila → `POST /api/queue/play`. Editar (SPEC 12): cada fila tiene ↑/↓/✕ (↑ deshabilitado en la primera, ↓ en la última de la cola) que mueven o quitan la pista por su `id` de MPD; "Limpiar" en el encabezado (oculto con la cola vacía) pide `confirm` y vacía la cola. Tras cada edición exitosa la cola se recarga. "Guardar como lista" (SPEC 13), junto a "Limpiar" y oculto con la cola vacía: `prompt` del nombre → `POST /api/queue/save`; muestra "Cola guardada como “<nombre>”".
- `main.py`: logs `ready:` / `button <nombre>` / `seek <N>` / warnings; SIGTERM → exit 0. Unidad `deploy/openplayer-web.service` (usuario `openplayer`). Pruebas en `tests/web-agent`.

Contrato HTTP:

| Método y ruta | Éxito | Errores |
|---|---|---|
| `GET /` | `200` `text/html` | — |
| `POST /api/buttons/<nombre>` (los 6 de §8) | `204` | `404` nombre desconocido; `503` Service inalcanzable |
| `POST /api/seek` con cuerpo `{"positionSeconds": N}` | `204` | `400` cuerpo ausente, > 1 KB, JSON inválido, o `positionSeconds` no entero / fuera de 0–86400; `503` Service inalcanzable |
| `GET /api/snapshot` | `200` `application/json`: la línea `player.snapshot` de §7 tal cual | `502` si el Service responde `error`; `503` inalcanzable o sin respuesta en 2 s |
| `GET /api/events` (SPEC 16) | `200` `text/event-stream`, `Cache-Control: no-store`: primero la última línea conocida, luego `data: <línea>` por cambio (`player.snapshot` o `error`, §7) y `: ping` cada 15 s sin eventos | `503` con 8 páginas abiertas |
| Biblioteca, playlists y cola (SPEC 10 a 13, tabla abajo) | `200` JSON (página o lista) / `204` (`ok`) | `400` forma inválida; `502` el Service responde `error` (cuerpo = esa línea); `503` inalcanzable o sin respuesta en 5 s |
| Otra ruta / otro método | — | `404` / `405` |
| Cliente fuera de los rangos | — | `403` en todas las rutas |

Rutas de biblioteca y playlists (SPEC 10). `<nombre>` y `<pos>` van URL-encoded en la ruta; cuerpos JSON de hasta 4 KB. El web agent valida la forma (tipos, enteros ≥ 0, textos no vacíos); el contenido (caracteres de los nombres, longitudes, `query` ≥ 2) lo valida el Core y vuelve como `502`.

| Método y ruta | Mensaje IPC (§7) | Éxito |
|---|---|---|
| `GET /api/library?path=&offset=` | `library.browse` | `200` `library.page` |
| `GET /api/library/search?q=&offset=` | `library.search` | `200` `library.page` |
| `POST /api/library/play` `{"uri"}` | `library.play` | `204` |
| `GET /api/playlists` | `playlist.list` | `200` |
| `POST /api/playlists` `{"name"}` | `playlist.create` | `204` |
| `GET /api/playlists/<nombre>?offset=` | `playlist.get` | `200` `library.page` |
| `POST /api/playlists/<nombre>/rename` `{"newName"}` | `playlist.rename` | `204` |
| `DELETE /api/playlists/<nombre>` | `playlist.delete` | `204` |
| `POST /api/playlists/<nombre>/tracks` `{"uri"}` | `playlist.add` | `204` |
| `DELETE /api/playlists/<nombre>/tracks/<pos>` | `playlist.remove` | `204` |
| `POST /api/playlists/<nombre>/move` `{"from","to"}` | `playlist.move` | `204` |
| `POST /api/playlists/<nombre>/play` `{"position"}` opcional (cuerpo opcional) | `playlist.play` | `204` |
| `GET /api/queue?offset=` (SPEC 11) | `queue.get` | `200` `queue.page` |
| `POST /api/queue/play` `{"position"}` (SPEC 11) | `queue.play` | `204` |
| `DELETE /api/queue/tracks/{id}` (SPEC 12) | `queue.remove` | `204` |
| `POST /api/queue/move` `{"id","to"}` (SPEC 12) | `queue.move` | `204` |
| `DELETE /api/queue` (SPEC 12) | `queue.clear` | `204` |
| `POST /api/queue/tracks` `{"uri","next"}` (SPEC 13; `next` booleano opcional) | `queue.add` | `204` |
| `POST /api/queue/save` `{"name"}` (SPEC 13) | `queue.save` | `204` |

### MPD y salida de audio

MPD administra la biblioteca, la cola y la reproducción. Para el primer hito, seleccionar el DAC USB mediante ALSA. No codificar un índice de tarjeta fijo: inspeccionar `aplay -l` y `/proc/asound/cards` y configurar el `audio_output` con el id de la tarjeta, `hw:CARD=<id>,DEV=0` (`Device` en el DAC validado; ver `assembly.md` §4–5). Bluetooth A2DP puede requerir PipeWire/WirePlumber o una configuración equivalente de la distribución. Validar la ruta de audio en el sistema operativo elegido antes de implementar un selector automático.

## 6. Contratos sugeridos

Interfaz inicial orientativa en C#:

```csharp
public interface IPlayer
{
    Task PlayAsync(CancellationToken ct = default);
    Task PauseAsync(CancellationToken ct = default);
    Task TogglePlaybackAsync(CancellationToken ct = default);
    Task NextAsync(CancellationToken ct = default);
    Task PreviousAsync(CancellationToken ct = default);
    Task SeekAsync(TimeSpan position, CancellationToken ct = default);
    Task SetVolumeAsync(int volume, CancellationToken ct = default);
    Task<PlaybackSnapshot> GetSnapshotAsync(CancellationToken ct = default);
    Task WaitForChangeAsync(CancellationToken ct = default);   // idle player (SPEC 15)
}
```

`SeekAsync` mueve la posición dentro de la pista actual (MPD: `seekcur`); `previous` lo usa para reiniciar la pista. `SetVolumeAsync` acepta 0–100 y las implementaciones validan con `Volume.EnsureValid`.

`PlaybackSnapshot` debe incluir como mínimo estado, pista actual nullable, posición, duración, volumen y timestamp de actualización. Usar `TimeSpan` para posiciones/duraciones. No asumir que todos los metadatos existen.

`ILibrary` debe ofrecer búsquedas acotadas y paginables cuando sea posible. `IPlaylistStore` puede delegar inicialmente todas las listas persistentes a MPD; no crear una segunda copia de la cola sin una necesidad concreta.

Implementado en SPEC 10 (`OpenPlayer.Core.Interfaces`, adaptadores `MpdLibrary` y `MpdPlaylistStore`):

```csharp
public interface ILibrary
{
    Task<LibraryPage> BrowseAsync(string path, int offset, CancellationToken ct = default);   // lsinfo; "" = raíz
    Task<LibraryPage> SearchAsync(string query, int offset, CancellationToken ct = default);  // search any
    Task PlayTrackAsync(string uri, CancellationToken ct = default);                          // clear + add + play 0
}

public interface IPlaylistStore
{
    Task<IReadOnlyList<string>> ListAsync(CancellationToken ct = default);
    Task<LibraryPage> GetAsync(string name, int offset, CancellationToken ct = default);
    Task CreateAsync(string name, CancellationToken ct = default);          // existe → error; si no, playlistadd "" + playlistclear (MPD 0.23)
    Task RenameAsync(string name, string newName, CancellationToken ct = default);
    Task DeleteAsync(string name, CancellationToken ct = default);
    Task AddAsync(string name, string uri, CancellationToken ct = default); // pista o carpeta (recursivo)
    Task RemoveAsync(string name, int position, CancellationToken ct = default);
    Task MoveAsync(string name, int from, int to, CancellationToken ct = default);
    Task PlayAsync(string name, int position, CancellationToken ct = default); // clear + load + play N
}
```

- `LibraryPage(Offset, Total, Entries)` con páginas de `LibraryPage.PageSize` = 100; `LibraryEntry(Uri, Track?, Id?)` con `Track` null para carpetas; `Id` (SPEC 12) es el id de MPD de la pista en la cola (`playlistinfo`) y es null en biblioteca y playlists. En playlists, la posición de una pista es `Offset + índice`.
- MPD 0.23 no pagina `lsinfo` ni `search`: el adaptador pide todo y corta. `BrowseAsync` pone carpetas primero (orden estable) e ignora las entradas `playlist:`.
Implementado en SPEC 11 (adaptador `MpdQueue`): la cola de MPD es un contrato propio, distinto de la biblioteca y de las playlists guardadas.

```csharp
public interface IQueue
{
    Task<LibraryPage> GetAsync(int offset, CancellationToken ct = default);  // playlistinfo; posición = Offset + índice
    Task PlayAsync(int position, CancellationToken ct = default);           // play N
    Task RemoveAsync(int id, CancellationToken ct = default);               // deleteid ID (SPEC 12)
    Task MoveAsync(int id, int to, CancellationToken ct = default);         // moveid ID TO
    Task ClearAsync(CancellationToken ct = default);                        // clear
    Task AddAsync(string uri, bool next, CancellationToken ct = default);   // add URI [song+1] (SPEC 13)
    Task SaveAsync(string name, CancellationToken ct = default);            // save NAME
    Task EnableConsumeAsync(CancellationToken ct = default);                // consume 1 (SPEC 14)
    Task<IReadOnlyList<int>> IdsAsync(CancellationToken ct = default);      // plchangesposid 0: ids en orden
    Task RestoreAsync(string uri, CancellationToken ct = default);          // add URI 0 + play 0 (SPEC 15)
}
```

- `PlaybackSnapshot` suma `QueuePosition` (`int?`, índice 0-based de la actual; MPD `status: song`) y `QueueVersion` (`long?`; MPD `status: playlist`, cambia con cada edición de la cola). Ausentes o no numéricos → `null`. SPEC 15 suma `SongId` (`int?`, MPD `status: songid`), con la misma regla.
- `WaitForChangeAsync` (SPEC 15): `MpdClient.IdleAsync` abre una conexión propia y envía `idle player`; solo la conexión y el saludo tienen timeout, la espera no. Cancelar cierra la conexión.

- Nombres de playlist: `PlaylistName.EnsureValid` (1–100 caracteres, sin `/`, `\`, `\n`, `\r` ni `.` inicial). Todo argumento de texto a MPD pasa por `MpdClient.Quote` (comillas dobles, `\` y `"` escapados).

## 7. IPC Python ↔ C#

Transporte inicial: Unix domain socket local, ruta propuesta `/run/openplayer/hardware.sock`. El directorio `/run/openplayer` debe crearse en el arranque mediante `systemd` (`RuntimeDirectory=openplayer`) y asignarse a un grupo dedicado. No usar `/tmp` como ruta de confianza a largo plazo.

Formato JSON Lines: un objeto JSON por línea UTF-8 terminada en `\n`. Implementado en `OpenPlayer.Service.IpcServer` (SPEC 03); el parser es `OpenPlayer.Core.Messages.IpcMessageParser`.

Mensajes de entrada:

```json
{"type":"button.pressed","button":"next","sequence":1}
{"type":"player.get_snapshot"}
{"type":"player.subscribe"}
{"type":"player.seek","positionSeconds":83}
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
{"type":"queue.get","offset":0}
{"type":"queue.play","position":3}
{"type":"queue.remove","id":17}
{"type":"queue.move","id":17,"to":2}
{"type":"queue.clear"}
{"type":"queue.add","uri":"Rock/AC DC","next":true}
{"type":"queue.save","name":"Viaje"}
```

- `type` obligatorio. Campos extra se ignoran.
- `button.pressed`: `button` obligatorio, uno de `play_pause`, `previous`, `next`, `volume_up`, `volume_down`, `menu` (exacto). `sequence` opcional (entero); solo se registra en el log. No hay respuesta.
- `player.get_snapshot`: responde una línea solo al cliente que la pidió.
- `player.subscribe` (SPEC 16): la conexión queda dedicada a la suscripción; el Service ya no lee sus pedidos (las líneas siguientes se ignoran) y la quita al cerrarse. Responde enseguida con el `player.snapshot` actual (o la línea `error` si MPD falla) y, tras cada `WaitForChangeAsync` del observador (SPEC 15), envía el mismo snapshot que usa para el historial; si el observador falla con MPD, envía `{"type":"error","request":"player.get_snapshot",...}` una vez por fallo. El envío ocurre fuera del lock global, en paralelo, con timeout de 2 s: un suscriptor cuya escritura falla o tarda más se descarta (warning `Subscriber dropped`) y se cierra, sin frenar a los demás ni a los comandos. Varios suscriptores a la vez (web agent y pantalla del hardware agent, SPEC 17).
- `player.get_cover` (SPEC 19): carátula de la pista actual; responde una línea `{"type":"player.cover","songId":17,"mime":"image/jpeg","data":"<base64>"}`. `data` es la imagen original (sin redimensionar): primero la incrustada (`readpicture`), si no la de la carpeta (`albumart`, p. ej. `cover.jpg`); `data` y `mime` `null` si no hay carátula, `songId` `null` sin pista actual. Más de 2 MB → `error` con `cover too large`; MPD caído → `error` como el resto. Corre fuera del lock global (no frena botones). Pide `binarylimit 1048576` en la misma conexión de cada trozo; si MPD no lo conoce, sigue con trozos de 8 KB.
- `player.seek` (SPEC 09): `positionSeconds` obligatorio, entero JSON 0–86400 (no `83.5`, `"83"` ni `true`). Ejecuta `IPlayer.SeekAsync` (`seekcur`) y registra `Seek to N s`. No hay respuesta; si MPD falla (detenido, posición fuera de la pista) solo registra warning `Seek failed: …`. No se recorta contra la duración.
- `library.*` y `playlist.*` (SPEC 10): **siempre responden una línea**, aunque sean inválidos. Validación en el Core: `name`/`newName` con `PlaylistName.EnsureValid`; `uri` 1–1024 caracteres y `path` 0–1024 (`""` = raíz), sin caracteres de control; `query` 2–100; `offset`, `position`, `from`, `to` enteros JSON ≥ 0 (`offset` y la `position` de `playlist.play` son opcionales, 0). Se ejecutan bajo el mismo lock global. `library.play` y `playlist.play` reemplazan la cola (`clear` + `consume 1` + `add`/`load` + `play N`; SPEC 14: `consume 1`, y `playlist.play` desde N > 0 borra antes las pistas 0..N−1 con `delete 0:N` y hace `play 0`).
- `queue.*` (SPEC 11): también responden siempre una línea. `queue.get`: `offset` entero JSON ≥ 0, opcional (0); responde `queue.page` y registra `queue.get ok (offset N)` (la única consulta que se registra: permite ver en `journalctl` que la web no sondea la cola). `queue.play`: `position` entero JSON ≥ 0, obligatorio; ejecuta `play N` y responde `ok`. SPEC 12: `queue.remove` (`id`), `queue.move` (`id`, `to`) y `queue.clear` editan por id de MPD (`deleteid`, `moveid`, `clear`); `id` y `to` enteros JSON ≥ 0, obligatorios; responden `ok`. El id no cambia al mover ni al quitar otras pistas: una cola vieja en la página da un `ACK` de id inexistente, nunca toca otra pista. SPEC 13: `queue.add` (`uri` como `library.play`; `next` booleano JSON opcional, `false`) agrega pista o carpeta (recursivo): al final con `add "<uri>"`; con `next`, `status` y luego `add "<uri>" <song+1>` en dos conexiones bajo el lock global (sin pista actual, al final). `add` con posición requiere MPD ≥ 0.23.3 (la Pi tiene 0.24.4). `queue.save` (`name` con `PlaylistName.EnsureValid`) ejecuta `save "<name>"`; si la lista existe, MPD responde `ACK` y nada se sobrescribe.
- Modo `consume` (SPEC 14): cada canción terminada o saltada sale de la cola y la actual queda primera. `consume` solo quita la canción que sonaba, así que saltar a la posición N (`queue.play`, `playlist.play`) borra antes las anteriores (`delete 0:N`) y hace `play 0`: la elegida queda primera. Siempre activo: `consume 1` va con cada play (`library.play`, `playlist.play`, `queue.play`) y el Service lo envía al arrancar (MPD caído → warning `consume failed`, sigue). Reemplaza el nombre de "lista cargada" de SPEC 11–13.
- Etiquetas de origen (SPEC 14): el Service recuerda en memoria (`_sources`, id de MPD → origen, bajo el lock global) de dónde vino cada canción, porque MPD no guarda metadatos propios por canción de la cola (`addtagid` solo sirve para remotas). `playlist.play` etiqueta toda la cola nueva con el nombre de la lista; `library.play`, "Biblioteca"; `queue.add` compara `IQueue.IdsAsync()` (`plchangesposid 0`) antes y después: los ids nuevos → "Biblioteca" y se descartan los que ya no están; `queue.clear` vacía el mapa. Renombrar o borrar una lista, `queue.save`, `queue.remove`, `queue.move` y `queue.play` no cambian etiquetas (son una foto del momento). Un mensaje que falla no cambia el mapa; si `IdsAsync` falla tras una acción exitosa, la respuesta es `ok` y las canciones quedan sin etiqueta. Se pierde al reiniciar el Service; lo agregado fuera de la web (`mpc add`) queda sin etiqueta.
- Historial de ⏮ (SPEC 15): un observador en segundo plano del Service repite snapshot → `WaitForChangeAsync`. Si cambia `SongId`, la canción anterior entra al historial (`uri` + su etiqueta de origen) solo si estuvo en `play` o `pause`. Últimas 50, solo en memoria (se pierde al reiniciar), bajo el lock global; sobrevive a `queue.clear`, `playlist.play` y `library.play`. MPD caído → warning `player watch failed` y reintento a los 5 s. Dos cambios entre despertares de `idle` pueden perder la canción del medio. SPEC 16: `idle player mixer playlist options` (canción, play/pausa, seek, volumen, ediciones de la cola y `consume`); un cambio sin `SongId` nuevo no toca el historial, solo genera un push.

Respuestas:

```json
{"type":"player.snapshot","state":"playing","trackTitle":"Example","trackArtist":"Artist","trackAlbum":"Album","positionSeconds":42,"durationSeconds":210,"volume":35,"queuePosition":3,"queueLength":12,"queueVersion":42,"displayMode":"track"}
{"type":"error","request":"player.get_snapshot","message":"MPD did not respond within 3000 ms"}
```

- `player.snapshot` (generado por `SnapshotMessage`): `state` es `playing` | `paused` | `stopped`. Todos los campos excepto `type` y `state` pueden ser `null` (sin pista, sin metadatos, MPD sin mixer); los `null` se escriben explícitamente. Segundos truncados a entero.
- `error` (generado por `ErrorMessage`): la consulta falló porque MPD no respondió o devolvió `ACK`, o (SPEC 10) el mensaje de biblioteca/playlists era inválido (`message`: `invalid <campo>`).
- SPEC 10: `ok` (`OkMessage`) para mutaciones y `*.play`; `library.page` (`LibraryPageMessage`) para `library.browse`, `library.search` y `playlist.get`, con carpetas `{"uri","directory":true}` y pistas con `title`, `artist`, `album`, `durationSeconds` (`null` explícitos); `playlist.list` (`PlaylistListMessage`).
- SPEC 11: `player.snapshot` suma `queuePosition` (0-based) y `queueVersion`, siempre presentes (`null` explícito si MPD no los da). `queue.page` (`QueuePageMessage`): `offset`, `total` y `entries` con los campos de una pista de `library.page`, sin `directory`. SPEC 12: cada entrada suma `id` (id de MPD; `null` explícito si falta). SPEC 14: sin `playlist`; cada entrada suma `source` (etiqueta de origen; `null` explícito si no tiene).
- SPEC 18: `player.snapshot` suma `trackAlbum`, `queueLength` (MPD `playlistlength`) y `displayMode` (`track` | `clock` | `art` desde SPEC 19, nunca `null`). `displayMode` no viene de MPD: lo guarda el Service en memoria (arranca en `track`) y lo alterna `menu`.

```json
{"type":"ok","request":"playlist.add"}
{"type":"library.page","offset":0,"total":2,"entries":[{"uri":"Rock/AC DC","directory":true},{"uri":"Rock/x.mp3","directory":false,"title":"X","artist":"A","album":null,"durationSeconds":210}]}
{"type":"playlist.list","playlists":["Viaje","Gym"]}
{"type":"queue.page","offset":0,"total":2,"entries":[{"uri":"A1.flac","id":17,"source":"Favoritas","title":"Rolling In The Deep","artist":"Adele","album":"21","durationSeconds":225},{"uri":"x.mp3","id":18,"source":null,"title":null,"artist":null,"album":null,"durationSeconds":null}]}
{"type":"error","request":"playlist.create","message":"Playlist 'Viaje' already exists"}
```

Framing y errores:

- El servidor lee bytes y parte por `\n`; un `\r` final se descarta y las líneas vacías se ignoran. Un mensaje puede llegar partido en varias lecturas y una lectura puede traer varios mensajes.
- Límite `ipc.maxMessageBytes` (por defecto 4096) medido en bytes sin contar el `\n`. Si se acumulan más bytes sin `\n`, se registra un warning y se cierra esa conexión; el cliente debe reconectar.
- JSON inválido, `type` desconocido, botón inválido, `sequence` no entero o `positionSeconds` inválido: warning en el log y la conexión sigue abierta. Nunca termina el proceso.
- Varios clientes a la vez (agente y `socat` de diagnóstico). Todos los comandos se ejecutan en serie con un lock global.
- No hay acknowledgements de `button.pressed` ni de `player.seek` (sí de los mensajes de SPEC 10 y 11); el log y el estado de MPD bastan para el MVP. No se aceptan comandos arbitrarios ni nombres de ejecutables.

Socket:

- Al arrancar se borra un archivo de socket viejo y, tras el bind, se aplican permisos `0660`. Si el directorio no existe, el Service sale con código 1: lo crea systemd (`RuntimeDirectory=openplayer`, `0770`, grupo `openplayer`) en cada arranque de la unidad (SPEC 04).
- Al detenerse (Ctrl+C, SIGTERM) deja de aceptar conexiones, cierra los clientes y borra el archivo.
- El cliente (agente) debe reconectar con espera incremental limitada, sin registrar cada intento en un bucle rápido.

## 8. Mapeo de botones

- `play_pause`: alterna reproducción/pausa.
- `previous`: si la posición actual es mayor que `PreviousRestartThreshold` (3 s por defecto), reinicia la pista (`SeekAsync(0)`); si no, o si la posición es desconocida, va a la pista anterior. Con `consume` (SPEC 14) no queda pista anterior en la cola: medido en la Pi (MPD 0.24.4), `previous` reinicia la actual sin quitarla, así que sin historial ⏮ reinicia la canción. Con historial (SPEC 15), hasta el umbral (o sin posición) el Service saca la última escuchada y la reproduce arriba de la cola (`IQueue.RestoreAsync`: `add URI 0` + `play 0`; medido en la Pi: con `consume` la que sonaba queda segunda), con su etiqueta de origen. Un cambio causado por ⏮ no entra al historial (⏮⏮ retrocede dos canciones sin rebotar); la restaurada vuelve a entrar cuando termina. Si MPD rechaza el archivo (borrado), se descarta la entrada (warning `restore <uri> failed`) y ⏮ reinicia la actual. Mismo comportamiento en web y botón físico.
- `next`: siguiente pista.
- `volume_up` / `volume_down`: cambiar volumen en pasos de `VolumeStep` (5 por defecto), recortando a 0–100. Si el volumen es desconocido (MPD sin mixer), no hacer nada.
- `menu` (SPEC 18, 19): cicla `displayMode` de la pantalla redonda (`track` → `clock` → `art` → `track`) y empuja el snapshot a los suscriptores; no toca MPD. Lo atiende `IpcServer`, no `ButtonCommandHandler`.

Implementado en `OpenPlayer.Core.Commands.ButtonCommandHandler` (SPEC 01).

Las pulsaciones largas, combinaciones y doble clic son posteriores al MVP. Evitar que una misma pulsación genere tanto una acción corta como una larga.

## 9. Biblioteca, cola y listas

En v1, usar la base de biblioteca y las playlists de MPD. Implementar:

- Listado de pistas y búsqueda por texto.
- Estado de la cola y pista actual.
- Añadir pista a cola y limpiar cola con confirmación en interfaces futuras.
- Crear/listar/guardar playlists mediante el protocolo MPD.
- Tratar los URI/rutas como datos, nunca como shell commands.

Estado (SPEC 10, desde la web):

- Hecho: navegación por carpetas y búsqueda (`search any`), paginadas de a 100; playlists guardadas de MPD (`.m3u` en `playlist_directory`): crear, renombrar, borrar, agregar pista o carpeta, quitar, reordenar; reproducir una pista o una lista reemplazando la cola.
- Hecho (SPEC 11): ver la cola con la pista actual resaltada y saltar a una pista.
- Hecho (SPEC 12): editar la cola (quitar, reordenar, limpiar).
- Hecho (SPEC 13): agregar a la cola sin reemplazarla (al final o después de la actual) y guardar la cola como lista.
- Hecho (SPEC 14): cola independiente de su origen: `consume` (lo escuchado sale de la cola), etiqueta de origen por fila, ⏮ reinicia la actual.
- Hecho (SPEC 15): historial real para ⏮ (observador `idle player`, últimas 50 en memoria, la anterior vuelve arriba de la cola).
- Hecho (SPEC 16): actualización instantánea (observador `idle player mixer playlist options` → push `player.subscribe` → SSE `/api/events`); el sondeo de 2 s queda solo de respaldo.
- Pendiente: reproducir una lista sin borrar lo agregado (modelo tipo Spotify), arrastrar para reordenar en la cola y en Listas (asa ⠿ a la izquierda, Pointer Events sin librería, animación del lugar de destino antes de soltar), agregar a la cola desde Listas, refresco automático de la pestaña Listas (`idle stored_playlist`), navegación artista → álbum, menú en pantalla con botones (spec futura).
- Sin botón de reescaneo: `auto_update` de MPD (SPEC 07) indexa lo copiado por Samba.

Una base SQLite propia queda pospuesta para preferencias, historial de reproducción, ratings o datos que MPD no cubra.

## 10. Configuración

Archivo `config/player.example.json`; el build y el publish del Service lo copian como `player.json` junto al binario. Separar valores de despliegue (rutas, host/puerto MPD, socket) de preferencias (volumen inicial, pasos de volumen, salida preferida). No guardar contraseñas ni claves en el repositorio. Validar configuración al arrancar y mostrar errores accionables: si `player.json` falta o un valor es inválido, el Service sale con código 1 y un mensaje que nombra el archivo o el campo.

| Clave | Uso | Estado |
|---|---|---|
| `mpd.host` / `mpd.port` | Dirección de MPD (por defecto `127.0.0.1:6600`) | Usado |
| `mpd.connectTimeoutMs` | Timeout de cada operación MPD (conexión + respuesta) | Usado |
| `player.volumeStep` | Paso de `volume_up`/`volume_down`, 1–100 | Usado |
| `player.previousRestartThresholdSeconds` | Umbral de `previous` para reiniciar la pista | Usado |
| `player.initialVolume` | Volumen al arrancar, 0–100 | Validado, aún no aplicado |
| `player.preferredOutput` / `player.resumePlaybackOnBoot` | Salida preferida / reanudar al arrancar | Reservado |
| `ipc.unixSocketPath` | Ruta del socket Unix; el directorio debe existir | Usado |
| `ipc.maxMessageBytes` | Tamaño máximo de un mensaje IPC, 256–65536 bytes | Usado |
| `hardware.buttons` / `hardware.debounceSeconds` | Pines BCM y debounce de los botones | Usado (agente) |
| `hardware.display` | Pantalla GC9A01: `enabled` (por defecto `false`), `spiBus`/`spiDevice` 0–1, `dc`/`rst` BCM, `spiHz` 1–62,5 MHz (40 MHz por defecto), `rotation` 0/90/180/270 (180 por defecto, validado en la Pi). Opcional: sin la sección no hay pantalla | Usado (agente) |
| `web.port` | Puerto HTTP del web agent, 1024–65535 (por defecto 8080); `install.sh` lo agrega si falta | Usado (web agent) |

El Service abre una conexión TCP a MPD por operación (sin conexión persistente ni reconexión con backoff); un MPD caído solo hace fallar esa operación con un warning.

## 11. Logging y errores

- C# usa `Microsoft.Extensions.Logging` con salida a journald mediante stdout/stderr cuando corre bajo systemd.
- Python escribe logs a stdout/stderr o al journal; no crear logs ilimitados en la SD.
- Incluir componente, evento, operación y excepción; no registrar credenciales.
- Errores recuperables (MPD desconectado) no deben finalizar el proceso.
- Errores de configuración deben impedir el arranque con un mensaje claro.

## 12. Pruebas

Unitarias C#:

- Validación de volumen (0–100).
- Traducción de eventos de botones a comandos.
- Manejo de estado sin pista o sin duración.
- Errores y cancelación de adaptadores.

Python:

- Pruebas con botones simulados o mocks.
- Codificación/decodificación JSON Lines.
- Reconexión de socket y mensajes malformados.

Integración en Pi:

- MPD reproduce MP3 y FLAC.
- Controles `mpc` funcionan por SSH.
- Botón no genera dobles eventos.
- Reiniciar MPD no mata el servicio.
- Reiniciar el servicio permite reconectar el agente.

## 13. Fases de desarrollo

1. Instalar Raspberry Pi OS Lite, SSH, MPD y verificar DAC USB. *(Hecho.)*
2. Crear solución .NET, Core e interfaz `IPlayer`. *(Hecho: SPEC 01.)*
3. Implementar adaptador MPD y snapshot de estado. *(Hecho: SPEC 02.)*
4. Implementar socket Unix y agente Python con dos botones. *(Hecho: socket SPEC 03, agente SPEC 05 con los 6 botones; validado con cable de puente, botones físicos pendientes.)*
5. Añadir biblioteca y playlists. *(Web: SPEC 10 a 14; menú en pantalla + botones: spec futura.)*
6. Instalar servicios systemd y validar arranque automático. *(Hecho: SPEC 04 `deploy/openplayer.service`, SPEC 05 `deploy/openplayer-hardware.service`.)*
7. Configurar Bluetooth A2DP y selector de salida.
8. Añadir pantalla. *(SPEC 17: GC9A01 redonda por SPI, solo pista actual; carátula y menú pendientes.)*
9. Medir consumo y desarrollar alimentación portátil segura.
10. Diseñar carcasa 3D y consolidar cableado en PCB/perfboard.

## 14. Criterios de aceptación del MVP

- Reproduce archivos locales MP3 y FLAC por DAC USB.
- `play_pause` y `next` funcionan desde botones físicos.
- El servicio se recupera de un reinicio de MPD.
- SSH permite consultar estado y diagnosticar audio.
- El agente Python no depende directamente de MPD.
- El Core puede probarse sin Raspberry Pi.
- Los servicios arrancan automáticamente y registran errores en journal.

## 15. Instrucciones para LLMs/agentes de código

Antes de editar:

1. Leer este archivo, `gpio-map.md`, `battery-design.md` y `assembly.md` según el alcance.
2. Inspeccionar el árbol y el código existente; no asumir que un archivo está implementado solo porque aparezca en el árbol.
3. Identificar qué decisiones están validadas y cuáles están pendientes.
4. Proponer un cambio incremental, incluir pruebas y actualizar documentación.
5. No introducir servicios, frameworks o bases de datos adicionales sin justificar el beneficio.
6. No realizar cambios de hardware que contradigan límites eléctricos documentados.
7. Al finalizar, resumir archivos cambiados, pruebas ejecutadas, comandos pendientes y limitaciones conocidas.
