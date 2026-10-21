# Architecture — OpenPlayer

**Estado:** diseño inicial v1.0; algunas decisiones deben validarse en el dispositivo real.

## 1. Propósito

OpenPlayer es un reproductor de música local modular para Raspberry Pi Zero 2 W. Debe funcionar sin monitor ni teclado después de configurarse. La primera versión prioriza audio fiable, controles físicos y administración por SSH. OLED, Bluetooth como salida y batería integrada son fases posteriores.

## 2. Hardware conocido y objetivos

- Raspberry Pi Zero 2 W.
- microSD de 32 GB.
- DAC USB existente con jack de 3.5 mm.
- Protoboard, cables Dupont y botones momentáneos.
- Impresora 3D para la carcasa.
- Pantalla OLED SSD1306 I²C opcional, 128x64, en fase posterior.
- Bluetooth integrado de la Pi; objetivo: salida a auriculares mediante A2DP.
- Alimentación portátil futura. Durante el desarrollo inicial, usar fuente USB estable o power bank validado.

No se ha confirmado el modelo exacto del DAC, la distribución de Raspberry Pi OS, el modelo de batería ni el circuito de carga. Descubrir y documentar esos datos antes de cerrar configuraciones específicas.

## 3. Principios arquitectónicos

1. **Separación por capas:** dominio y contratos no dependen de hardware ni de MPD.
2. **MPD como motor de reproducción:** no desarrollar decodificadores propios en la primera versión.
3. **Una sola fuente de verdad:** MPD es autoridad para canción, cola, estado, posición y volumen cuando este último lo controla MPD.
4. **C# como orquestador:** valida comandos/eventos, coordina adaptadores y publica el estado.
5. **Python como agente de hardware:** lee GPIO, aplica debounce y emite eventos; en el futuro también actualiza OLED a partir del estado recibido.
6. **Interfaces reemplazables:** el hardware no invoca MPD directamente.
7. **Seguridad local:** MPD y IPC solo deben estar disponibles para procesos locales o usuarios/grupos autorizados.
8. **Resiliencia:** los servicios se reinician ante fallos, reconectan y registran errores sin bucles de log descontrolados.

## 4. Diagrama lógico

```text
[Botones GPIO] ---> [Hardware Agent: Python] -- JSON Lines / Unix socket --+
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
- En la fase OLED, dibuja el estado recibido o consultado por un canal definido; no consulta MPD directamente.
- Debe permitir simulación o pruebas sin hardware real.

Implementado en SPEC 05 (Python 3, solo stdlib y `gpiozero` con `lgpio`, paquetes del sistema, sin venv):

- `config.py`: lee `hardware.buttons`, `hardware.debounceSeconds` e `ipc.unixSocketPath` de `player.json`; config inválida → exit 1 nombrando el campo.
- `buttons.py`: un `gpiozero.Button` por pin (pull-up, `bounce_time` = debounce, aplicado por `lgpio`); el callback solo encola.
- `sender.py`: hilo que envía `button.pressed` con `sequence` por proceso. Reconexión con espera incremental 0.5–10 s; registra solo `connected`/`disconnected`; detecta el cierre del Service en reposo (`select`). Sin conexión, la pulsación se descarta (no se reenvía).
- `main.py`: entrada; SIGTERM/Ctrl+C → exit 0.
- Unidad `deploy/openplayer-hardware.service` (usuario `openplayer`, grupo `gpio`), instalada por `deploy/install.sh`. Pruebas en `tests/hardware-agent` con `MockFactory` y un servidor TCP local.

### `src/web-agent`

Proceso Python (SPEC 08, solo stdlib): página con los 6 botones y el estado, para controlar el reproductor desde un navegador de la red local sin GPIO.

- `config.py`: lee `ipc.unixSocketPath` y `web.port` (1024–65535) de `player.json`; ignora `hardware`. Config inválida → exit 1 nombrando el campo.
- `ipc.py`: una conexión al socket por pedido HTTP; `button.pressed` sin `sequence`; `player.get_snapshot` con timeout de 2 s; `player.seek` (SPEC 09). Biblioteca, playlists (SPEC 10) y cola (SPEC 11) con `request()`: timeout de 5 s y respuesta de hasta 1 MB.
- `server.py`: `ThreadingHTTPServer` en `::` (IPv4 e IPv6). Solo acepta clientes de `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `::1` y `fe80::/10` (IPv4 mapeadas se evalúan como IPv4); el resto recibe `403`. Sin autenticación ni HTTPS.
- `index.html`: botones y línea de estado (sondeo cada 2 s); título y artista se insertan como texto, nunca como HTML. Barra de progreso (`<input type="range">` + `m:ss / m:ss`, SPEC 09): avanza localmente entre sondeos si `playing`, el sondeo no la mueve mientras se arrastra, al soltar envía `POST /api/seek`; oculta sin `durationSeconds`, deshabilitada en `stopped`.
- Pestañas Reproductor / Biblioteca / Listas (SPEC 10). Biblioteca: carpetas con migas, búsqueda (≥ 2 caracteres), "Más" cada 100; tocar una pista reemplaza la cola y la reproduce; "+" agrega pista o carpeta a una lista (`<dialog>`). Listas: crear/renombrar con `prompt`, borrar con `confirm`; abrir una lista: ↑/↓/✕ y reproducir desde el inicio o desde una pista. Tras cada cambio la lista se recarga para no usar posiciones viejas.
- Panel "Cola" (SPEC 11): a la derecha en todas las pestañas con ventana ≥ 900 px; más angosta, debajo de los controles solo en Reproductor. Encabezado "Lista: <nombre>" o "Cola" + "· N canciones"; filas con número, título (o nombre de archivo), "artista · álbum" y m:ss. La cola se pide solo cuando el snapshot trae otro `queueVersion` (o tras renombrar/borrar una lista desde la página, o al recuperar la conexión): páginas desde 0 hasta incluir `queuePosition`, luego "Más". En cada sondeo se mueve el resaltado de la actual (color + 3 barras CSS: animadas en `playing`, congeladas en `paused`, ocultas en `stopped`, quietas con `prefers-reduced-motion`) y se centra si no está visible, salvo 10 s después de que el usuario desplace el panel. Tocar una fila → `POST /api/queue/play`.
- `main.py`: logs `ready:` / `button <nombre>` / `seek <N>` / warnings; SIGTERM → exit 0. Unidad `deploy/openplayer-web.service` (usuario `openplayer`). Pruebas en `tests/web-agent`.

Contrato HTTP:

| Método y ruta | Éxito | Errores |
|---|---|---|
| `GET /` | `200` `text/html` | — |
| `POST /api/buttons/<nombre>` (los 6 de §8) | `204` | `404` nombre desconocido; `503` Service inalcanzable |
| `POST /api/seek` con cuerpo `{"positionSeconds": N}` | `204` | `400` cuerpo ausente, > 1 KB, JSON inválido, o `positionSeconds` no entero / fuera de 0–86400; `503` Service inalcanzable |
| `GET /api/snapshot` | `200` `application/json`: la línea `player.snapshot` de §7 tal cual | `502` si el Service responde `error`; `503` inalcanzable o sin respuesta en 2 s |
| Biblioteca, playlists y cola (SPEC 10 y 11, tabla abajo) | `200` JSON (página o lista) / `204` (`ok`) | `400` forma inválida; `502` el Service responde `error` (cuerpo = esa línea); `503` inalcanzable o sin respuesta en 5 s |
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

- `LibraryPage(Offset, Total, Entries)` con páginas de `LibraryPage.PageSize` = 100; `LibraryEntry(Uri, Track?)` con `Track` null para carpetas. En playlists, la posición de una pista es `Offset + índice`.
- MPD 0.23 no pagina `lsinfo` ni `search`: el adaptador pide todo y corta. `BrowseAsync` pone carpetas primero (orden estable) e ignora las entradas `playlist:`.
Implementado en SPEC 11 (adaptador `MpdQueue`): la cola de MPD es un contrato propio, distinto de la biblioteca y de las playlists guardadas.

```csharp
public interface IQueue
{
    Task<LibraryPage> GetAsync(int offset, CancellationToken ct = default);  // playlistinfo; posición = Offset + índice
    Task PlayAsync(int position, CancellationToken ct = default);           // play N
}
```

- `PlaybackSnapshot` suma `QueuePosition` (`int?`, índice 0-based de la actual; MPD `status: song`) y `QueueVersion` (`long?`; MPD `status: playlist`, cambia con cada edición de la cola). Ausentes o no numéricos → `null`.

- Nombres de playlist: `PlaylistName.EnsureValid` (1–100 caracteres, sin `/`, `\`, `\n`, `\r` ni `.` inicial). Todo argumento de texto a MPD pasa por `MpdClient.Quote` (comillas dobles, `\` y `"` escapados).

## 7. IPC Python ↔ C#

Transporte inicial: Unix domain socket local, ruta propuesta `/run/openplayer/hardware.sock`. El directorio `/run/openplayer` debe crearse en el arranque mediante `systemd` (`RuntimeDirectory=openplayer`) y asignarse a un grupo dedicado. No usar `/tmp` como ruta de confianza a largo plazo.

Formato JSON Lines: un objeto JSON por línea UTF-8 terminada en `\n`. Implementado en `OpenPlayer.Service.IpcServer` (SPEC 03); el parser es `OpenPlayer.Core.Messages.IpcMessageParser`.

Mensajes de entrada:

```json
{"type":"button.pressed","button":"next","sequence":1}
{"type":"player.get_snapshot"}
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
```

- `type` obligatorio. Campos extra se ignoran.
- `button.pressed`: `button` obligatorio, uno de `play_pause`, `previous`, `next`, `volume_up`, `volume_down`, `menu` (exacto). `sequence` opcional (entero); solo se registra en el log. No hay respuesta.
- `player.get_snapshot`: responde una línea solo al cliente que la pidió.
- `player.seek` (SPEC 09): `positionSeconds` obligatorio, entero JSON 0–86400 (no `83.5`, `"83"` ni `true`). Ejecuta `IPlayer.SeekAsync` (`seekcur`) y registra `Seek to N s`. No hay respuesta; si MPD falla (detenido, posición fuera de la pista) solo registra warning `Seek failed: …`. No se recorta contra la duración.
- `library.*` y `playlist.*` (SPEC 10): **siempre responden una línea**, aunque sean inválidos. Validación en el Core: `name`/`newName` con `PlaylistName.EnsureValid`; `uri` 1–1024 caracteres y `path` 0–1024 (`""` = raíz), sin caracteres de control; `query` 2–100; `offset`, `position`, `from`, `to` enteros JSON ≥ 0 (`offset` y la `position` de `playlist.play` son opcionales, 0). Se ejecutan bajo el mismo lock global. `library.play` y `playlist.play` reemplazan la cola (`clear` + `add`/`load` + `play N`).
- `queue.*` (SPEC 11): también responden siempre una línea. `queue.get`: `offset` entero JSON ≥ 0, opcional (0); responde `queue.page` y registra `queue.get ok (offset N)` (la única consulta que se registra: permite ver en `journalctl` que la web no sondea la cola). `queue.play`: `position` entero JSON ≥ 0, obligatorio; ejecuta `play N` y responde `ok`.
- Nombre de la lista cargada (SPEC 11): el Service lo recuerda en memoria (`_loadedPlaylist`, bajo el lock global) porque MPD no lo guarda. Lo fija un `playlist.play` exitoso, lo borra `library.play`, lo actualiza `playlist.rename` y lo borra `playlist.delete` si nombran esa lista. Un mensaje que falla no lo cambia. Se pierde al reiniciar el Service y puede quedar viejo si la cola cambia fuera de la web (`mpc`).

Respuestas:

```json
{"type":"player.snapshot","state":"playing","trackTitle":"Example","trackArtist":"Artist","positionSeconds":42,"durationSeconds":210,"volume":35,"queuePosition":3,"queueVersion":42}
{"type":"error","request":"player.get_snapshot","message":"MPD did not respond within 3000 ms"}
```

- `player.snapshot` (generado por `SnapshotMessage`): `state` es `playing` | `paused` | `stopped`. Todos los campos excepto `type` y `state` pueden ser `null` (sin pista, sin metadatos, MPD sin mixer); los `null` se escriben explícitamente. Segundos truncados a entero.
- `error` (generado por `ErrorMessage`): la consulta falló porque MPD no respondió o devolvió `ACK`, o (SPEC 10) el mensaje de biblioteca/playlists era inválido (`message`: `invalid <campo>`).
- SPEC 10: `ok` (`OkMessage`) para mutaciones y `*.play`; `library.page` (`LibraryPageMessage`) para `library.browse`, `library.search` y `playlist.get`, con carpetas `{"uri","directory":true}` y pistas con `title`, `artist`, `album`, `durationSeconds` (`null` explícitos); `playlist.list` (`PlaylistListMessage`).
- SPEC 11: `player.snapshot` suma `queuePosition` (0-based) y `queueVersion`, siempre presentes (`null` explícito si MPD no los da). `queue.page` (`QueuePageMessage`): `playlist` (nombre recordado o `null`), `offset`, `total` y `entries` con los campos de una pista de `library.page`, sin `directory`.

```json
{"type":"ok","request":"playlist.add"}
{"type":"library.page","offset":0,"total":2,"entries":[{"uri":"Rock/AC DC","directory":true},{"uri":"Rock/x.mp3","directory":false,"title":"X","artist":"A","album":null,"durationSeconds":210}]}
{"type":"playlist.list","playlists":["Viaje","Gym"]}
{"type":"queue.page","playlist":"Favoritas","offset":0,"total":2,"entries":[{"uri":"A1.flac","title":"Rolling In The Deep","artist":"Adele","album":"21","durationSeconds":225},{"uri":"x.mp3","title":null,"artist":null,"album":null,"durationSeconds":null}]}
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
- `previous`: si la posición actual es mayor que `PreviousRestartThreshold` (3 s por defecto), reinicia la pista (`SeekAsync(0)`); si no, o si la posición es desconocida, va a la pista anterior.
- `next`: siguiente pista.
- `volume_up` / `volume_down`: cambiar volumen en pasos de `VolumeStep` (5 por defecto), recortando a 0–100. Si el volumen es desconocido (MPD sin mixer), no hacer nada.
- `menu`: reservado para navegación OLED futura; en el MVP no hace nada.

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
- Pendiente: editar la cola (quitar, reordenar, limpiar), actualización instantánea (`idle` → SSE), navegación artista → álbum, OLED y botones (spec futura).
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
| `hardware.*` | Pines BCM, debounce, OLED; los lee el agente Python | Reservado (agente) |
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
5. Añadir biblioteca y playlists. *(Web: SPEC 10 y 11; OLED + botones: spec futura.)*
6. Instalar servicios systemd y validar arranque automático. *(Hecho: SPEC 04 `deploy/openplayer.service`, SPEC 05 `deploy/openplayer-hardware.service`.)*
7. Configurar Bluetooth A2DP y selector de salida.
8. Añadir OLED.
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
