# SPEC 02 — Adaptador MPD y Service mínimo por stdin

> **Status:** Implemented
> **Depends on:** SPEC 01
> **Date:** 2026-10-20
> **Objective:** Implementar `OpenPlayer.Mpd` (`IPlayer` sobre el protocolo MPD) y un `OpenPlayer.Service` de consola que ejecuta botones y `status` leídos por stdin, verificable por SSH en la Pi.

## Scope

**In:**

- Proyecto `src/OpenPlayer.Mpd` (classlib; referencia solo Core, sin paquetes NuGet).
- Cliente MPD mínimo sobre `TcpClient`, con **una conexión por operación**: conectar, leer el saludo `OK MPD <versión>`, enviar los comandos, leer hasta `OK` o `ACK` y cerrar.
- `MpdPlayer : IPlayer` con los comandos `status`, `currentsong`, `play`, `pause 0|1`, `next`, `previous`, `seekcur`, `setvol`.
- `TogglePlaybackAsync` consulta `status` y decide entre `pause 1`, `pause 0` y `play`.
- Mapeo de `status` y `currentsong` a `PlaybackSnapshot`; `volume:-1` se traduce a `null`.
- `ACK` → `MpdException` con el mensaje de MPD; un fallo de red → `MpdUnavailableException`.
- Timeout de conexión y lectura con `mpd.connectTimeoutMs`.
- `SnapshotMessage` en Core: `PlaybackSnapshot` → JSON `player.snapshot`, con el campo nuevo `trackArtist`.
- Proyecto `src/OpenPlayer.Service` (consola con `Microsoft.Extensions.Hosting`).
- Lectura de `player.json` junto al binario, solo las secciones `mpd` y `player`. Si el archivo falta o algún valor es inválido, sale con exit code 1 y un mensaje claro.
- El build y el publish copian `config/player.example.json` como `player.json`.
- Bucle stdin:
  - Los 6 nombres IPC ejecutan `ButtonCommandHandler`.
  - `status` imprime una línea JSON `player.snapshot`.
  - `quit`, EOF o Ctrl+C salen con exit code 0.
  - Un comando desconocido registra un warning y el bucle sigue.
- Si falla una operación MPD, se registra un warning de una línea, no se reintenta y el proceso sigue.
- En `config/player.example.json`: quitar `reconnectInitialDelayMs` y `reconnectMaxDelayMs`, y añadir `previousRestartThresholdSeconds`.
- Proyecto `tests/OpenPlayer.Mpd.Tests` (xUnit): parseo puro y servidor MPD falso con `TcpListener`.
- Publish `linux-arm64` autocontenido en carpeta, y verificación manual en la Pi por SSH.
- Actualizar `docs/architecture.md` §7 (`trackArtist`) y §10 (claves de configuración), `README.md` (cómo ejecutar y publicar) y `docs/assembly.md` §7 (comando de publish).

**Out of scope (para futuras specs):**

- IPC por socket Unix con el hardware agent (SPEC 03).
- Unit systemd, usuario `openplayer` y `/opt/openplayer` (spec de despliegue).
- Aplicar `initialVolume` o `resumePlaybackOnBoot` al arrancar.
- Conexión persistente, `idle` y publicación automática de cambios de estado.
- `ILibrary`, `IPlaylistStore`, cola, búsqueda y escape de argumentos de texto (no se envían strings a MPD en esta spec).
- Pantalla o menú de configuración y preferencias persistentes editables.
- Contraseña de MPD.
- Cualquier cambio en `deploy/`.

## Data model

Archivos nuevos:

```text
src/OpenPlayer.Mpd/
  MpdOptions.cs              // Host, Port, ConnectTimeout + validación
  MpdClient.cs               // una conexión por llamada: saludo, comandos, OK/ACK
  MpdResponse.cs             // pares clave/valor de una respuesta
  MpdSnapshotParser.cs       // status + currentsong → PlaybackSnapshot
  MpdExceptions.cs           // MpdException, MpdUnavailableException
  MpdPlayer.cs               // IPlayer sobre MpdClient
src/OpenPlayer.Core/
  Messages/SnapshotMessage.cs // PlaybackSnapshot → JSON player.snapshot
src/OpenPlayer.Service/
  Program.cs                 // Generic Host, carga y validación de player.json
  PlayerConfig.cs            // POCOs de las secciones "mpd" y "player"
  ConsoleCommandLoop.cs      // BackgroundService que lee stdin
tests/OpenPlayer.Mpd.Tests/
  MpdSnapshotParserTests.cs
  MpdClientTests.cs          // contra FakeMpdServer
  MpdPlayerTests.cs          // comandos enviados, contra FakeMpdServer
  FakeMpdServer.cs           // TcpListener en 127.0.0.1:0 con respuestas guionizadas
tests/OpenPlayer.Core.Tests/
  SnapshotMessageTests.cs
```

```csharp
public sealed record MpdOptions(string Host, int Port, TimeSpan ConnectTimeout);
// Host no vacío; Port 1–65535; ConnectTimeout > 0 → si no, ArgumentException

public sealed class MpdResponse(IReadOnlyList<KeyValuePair<string, string>> pairs)
{
    public string? Get(string key);   // primer valor o null
}

public sealed class MpdClient(MpdOptions options)
{
    // Abre la conexión, envía cada comando y devuelve una respuesta por comando. Cierra siempre.
    public Task<IReadOnlyList<MpdResponse>> ExecuteAsync(IReadOnlyList<string> commands, CancellationToken ct);
}

public class MpdException(string command, string message) : Exception(message);    // ACK
public class MpdUnavailableException(string message, Exception inner) : Exception(message, inner); // red/timeout/saludo

public static class MpdSnapshotParser
{
    public static PlaybackSnapshot Parse(MpdResponse status, MpdResponse currentSong, DateTimeOffset now);
}

public sealed class MpdPlayer(MpdClient client, TimeProvider time) : IPlayer;
```

Mapeo MPD → `PlaybackSnapshot`:

| MPD | Campo | Regla |
|---|---|---|
| `status.state` `play`/`pause`/`stop` | `State` | otro valor → `Stopped` |
| `status.elapsed` (segundos, decimal) | `Position` | ausente → `null` |
| `status.duration` | `Duration` | ausente → `null` |
| `status.volume` | `Volume` | `-1` o ausente → `null` |
| `currentsong.file` | `CurrentTrack.Uri` | sin `file` → `CurrentTrack = null` |
| `currentsong.Title` / `Artist` / `Album` | `Track.*` | ausente → `null` |

Números con `CultureInfo.InvariantCulture`. `seekcur 0` y `setvol N` se formatean también en invariante.

Comandos por método de `MpdPlayer`:

| Método | Comandos MPD |
|---|---|
| `PlayAsync` | `play` |
| `PauseAsync` | `pause 1` |
| `TogglePlaybackAsync` | `status`, y en otra conexión: `pause 1` si play, `pause 0` si pause, `play` si stop |
| `NextAsync` / `PreviousAsync` | `next` / `previous` |
| `SeekAsync(t)` | `seekcur <segundos>` |
| `SetVolumeAsync(v)` | `Volume.EnsureValid(v)` y luego `setvol <v>` |
| `GetSnapshotAsync` | `status` + `currentsong` en la misma conexión |

`player.json`, sección `player` (nuevo campo):

```json
"player": { "initialVolume": 35, "volumeStep": 5, "previousRestartThresholdSeconds": 3, ... }
```

Mensaje `status` (una línea, `System.Text.Json`, camelCase, nulls incluidos):

```json
{"type":"player.snapshot","state":"playing","trackTitle":"…","trackArtist":"…","positionSeconds":83,"durationSeconds":387,"volume":35}
```

`state` ∈ `playing` | `paused` | `stopped`. Los segundos se truncan a entero.

## Implementation plan

1. Crear `src/OpenPlayer.Mpd` (classlib → Core), `tests/OpenPlayer.Mpd.Tests` (xUnit → Mpd) y `src/OpenPlayer.Service` (consola → Core + Mpd, con `Microsoft.Extensions.Hosting`). Añadirlos a `OpenPlayer.slnx` y quitar los archivos de plantilla. Verificar: `dotnet build` y `dotnet test` en verde.
2. Añadir `MpdOptions`, `MpdResponse`, `MpdExceptions` y `MpdSnapshotParser`, con pruebas de parseo: los 3 estados, `volume:-1`, campos ausentes, sin `file`, decimales invariantes.
3. Añadir `FakeMpdServer` y `MpdClient`, con pruebas: saludo y `OK`; varios comandos en una conexión; `ACK` → `MpdException`; puerto cerrado → `MpdUnavailableException`; saludo inválido → `MpdUnavailableException`; servidor que no responde → timeout `MpdUnavailableException`.
4. Añadir `MpdPlayer`, con pruebas contra `FakeMpdServer`: comando exacto por método, `TogglePlayback` en sus 3 casos, `SetVolumeAsync(101)` lanza sin abrir conexión, `GetSnapshotAsync` en una sola conexión.
5. Añadir `src/OpenPlayer.Core/Messages/SnapshotMessage.cs` (`PlaybackSnapshot` → JSON `player.snapshot`), con pruebas en `OpenPlayer.Core.Tests`: snapshot completo, todo `null`, truncado de segundos, nombres de estado.
6. Actualizar `config/player.example.json` (quitar `reconnect*` y añadir `previousRestartThresholdSeconds`). Añadir `PlayerConfig` y `Program.cs`: cargar `player.json` desde `AppContext.BaseDirectory`, construir `MpdOptions` y `PlayerSettings`, y salir con exit code 1 si hay error. Copiar el ejemplo como `player.json` al compilar. Verificar a mano: sin `player.json` → exit code 1 con mensaje; con `volumeStep: 0` → exit code 1.
7. Añadir `ConsoleCommandLoop`: nombres IPC → `ButtonCommandHandler`, `status` → `SnapshotMessage`, `quit` y EOF → parada ordenada, comando desconocido → warning, excepción MPD → warning de una línea. Verificar a mano en Windows sin MPD: `status` da un warning y el proceso sigue; `quit` sale con exit code 0.
8. Actualizar `docs/architecture.md` §7 (`trackArtist`) y §10 (claves de configuración), `README.md` (ejecutar y publicar) y `docs/assembly.md` §7 (comando de publish autocontenido).

## Acceptance criteria

**Windows (automatizable):**

- [x] `dotnet build OpenPlayer.slnx` termina sin errores ni warnings.
- [x] `dotnet test OpenPlayer.slnx` pasa todas las pruebas (Core y Mpd).
- [x] `OpenPlayer.Core.csproj` y `OpenPlayer.Mpd.csproj` no tienen `PackageReference`.
- [x] Core y Mpd no referencian `Microsoft.Extensions.*` (verificable con grep).
- [x] `MpdSnapshotParser` traduce `volume:-1` a `Volume = null` y un `currentsong` sin `file` a `CurrentTrack = null`.
- [x] `MpdClient` lanza `MpdException` ante `ACK` y `MpdUnavailableException` ante puerto cerrado, saludo inválido o timeout.
- [x] Cada `MpdClient.ExecuteAsync` abre exactamente una conexión y la cierra al terminar, también si hay error.
- [x] `TogglePlaybackAsync` envía `pause 1` si el estado es play, `pause 0` si es pause y `play` si es stop.
- [x] `SetVolumeAsync(101)` lanza `ArgumentOutOfRangeException` sin abrir conexión.
- [x] `GetSnapshotAsync` envía `status` y `currentsong` en una sola conexión.
- [x] `SnapshotMessage` produce exactamente `{"type":"player.snapshot","state":…,"trackTitle":…,"trackArtist":…,"positionSeconds":…,"durationSeconds":…,"volume":…}`, con `null` en los campos ausentes.
- [x] Sin `player.json` junto al binario, el Service sale con exit code 1 y un mensaje que nombra el archivo.
- [x] Con `"volumeStep": 0` en `player.json`, el Service sale con exit code 1 y un mensaje que nombra el campo.
- [x] Con MPD inaccesible, `status` y `next` registran un warning de una línea y el proceso sigue leyendo stdin.
- [x] Un comando desconocido registra un warning y el proceso sigue.
- [x] `quit` y EOF (Ctrl+Z/Ctrl+D) terminan el proceso con exit code 0.
- [x] `config/player.example.json` no contiene `reconnectInitialDelayMs` ni `reconnectMaxDelayMs`, y contiene `previousRestartThresholdSeconds`.

**Raspberry Pi (manual por SSH; requiere fase 1 lista: MPD con al menos 2 pistas en cola):**

- [x] `dotnet publish src/OpenPlayer.Service -c Release -r linux-arm64 --self-contained true -o publish/linux-arm64` genera la carpeta con `player.json` incluido.
- [x] Tras copiar la carpeta a la Pi, `./OpenPlayer.Service` arranca sin tener el runtime de .NET instalado.
- [x] `status` imprime un `player.snapshot` cuyo `trackTitle` coincide con `mpc current`.
- [x] `play_pause` alterna entre `playing` y `paused` según `mpc status`.
- [x] `next` cambia la pista y `mpc current` lo confirma.
- [x] `previous` con más de 3 s de reproducción reinicia la pista; con menos de 3 s va a la anterior.
- [x] `volume_up` y `volume_down` cambian el volumen en 5, si el DAC tiene mixer; si no lo tiene, el volumen sale `null` y no hay error.
- [x] Tras `sudo systemctl restart mpd`, el siguiente `status` funciona sin reiniciar el Service.

**Documentación:**

- [x] `docs/architecture.md` §7 incluye `trackArtist` y §10 lista las claves de `player.json`.
- [x] `README.md` explica cómo ejecutar y publicar el Service.

## Decisions

- **Sí:** Service de larga duración que lee stdin. Se prueba por SSH sin GPIO ni socket; la SPEC 03 reemplaza stdin por el socket reutilizando `ButtonNames.TryParse` y `SnapshotMessage`.
- **No:** CLI de un solo uso (`OpenPlayer.Service next`). No sirve como base del servicio real.
- **No:** socket Unix en esta spec. Va en la SPEC 03 para mantener esta acotada.
- **Sí:** cliente MPD propio sobre `TcpClient`. Son unos 8 comandos, sin dependencias y con control total de errores y timeouts.
- **No:** librería NuGet de MPD (p. ej. MpcNET). Habría que verificar mantenimiento y compatibilidad con .NET 10 para muy poco protocolo.
- **Sí:** una conexión TCP por operación. Evita las conexiones cerradas por el `connection_timeout` de MPD (60 s) y hace que sobrevivir a un reinicio de MPD no requiera código extra. En localhost cuesta milisegundos.
- **No:** conexión persistente con `ping` o `idle`. Más estado y más código; se reconsidera cuando haya que publicar cambios de estado hacia la OLED.
- **Sí:** quitar `reconnectInitialDelayMs` y `reconnectMaxDelayMs` de la configuración. Sin conexión persistente no hay reconexión que temporizar (YAGNI).
- **Sí:** no reintentar comandos fallidos. Reintentar `next` a ciegas podría saltar dos pistas si el primero se ejecutó y solo se perdió la respuesta.
- **Sí:** `TogglePlaybackAsync` consulta `status` y envía `pause 1`, `pause 0` o `play`. `pause` sin argumento está deprecado en MPD y no arranca desde `stop`.
- **Sí:** `volume:-1` se traduce a `null`. MPD reporta -1 sin mixer; Core ya trata `null` como "no hacer nada".
- **Sí:** pruebas con `FakeMpdServer` (`TcpListener` en 127.0.0.1:0). Prueban el protocolo real (saludo, `OK`, `ACK`, cierre) en Windows sin MPD.
- **No:** MPD en WSL/Docker como criterio. La verificación real se hace en la Pi, que es el destino.
- **Sí:** Generic Host (`Microsoft.Extensions.Hosting`) solo en el Service. Aporta configuración, `ILogger`, DI y SIGTERM, y deja listo el paso a systemd.
- **Sí:** Core y Mpd sin `Microsoft.Extensions.*`. `MpdPlayer` no registra nada en logs: lanza excepciones y el Service las registra.
- **Sí:** `player.json` junto al binario, obligatorio y validado al arrancar. Una configuración inválida impide el arranque (`architecture.md` §10).
- **No:** `/etc/openplayer/player.json`. Pertenece a la spec de despliegue con systemd.
- **No:** aplicar `initialVolume` ni `resumePlaybackOnBoot` al arrancar. Evita efectos inesperados; va en la spec del servicio real.
- **Sí:** `previousRestartThresholdSeconds` en `player.json`. Hace configurable el umbral definido en la SPEC 01.
- **Sí:** `status` imprime JSON `player.snapshot`. Adelanta el contrato del IPC y se puede filtrar con `jq`.
- **Sí:** añadir `trackArtist` al snapshot. Solo el título no basta para identificar la canción.
- **Sí:** `SnapshotMessage` en Core. Es lógica serializable sin IO (`System.Text.Json` es BCL), se puede probar, y la SPEC 03 la reutiliza.
- **Sí:** publish autocontenido en carpeta. No requiere instalar el runtime en la Pi y es la base del futuro `/opt/openplayer`.
- **No:** `PublishSingleFile`. No aporta: `player.json` igual va aparte.
- **No:** pantalla de configuración en el player. Requiere OLED/menú o API, y preferencias escribibles; merece su propia spec.
- **No:** escape de argumentos de texto. Esta spec no envía strings a MPD; llega con biblioteca y búsqueda.

## Risks

| Riesgo | Mitigación |
|---|---|
| El DAC USB no expone mixer hardware y MPD reporta `volume:-1`; los botones de volumen no hacen nada. | Comportamiento esperado (no hay error). Si se quiere volumen, configurar `mixer_type "software"` en el `audio_output` de MPD; se documenta en la verificación de la Pi. |
| `FakeMpdServer` no reproduce exactamente el MPD real (formato de saludo, orden de campos). | Las respuestas del falso se copian de salidas reales de MPD; los criterios manuales en la Pi validan el protocolo de verdad. |
| Pruebas con `TcpListener` inestables en CI o con firewall en Windows. | Escuchar solo en `127.0.0.1` con puerto 0 (asignado por el SO) y timeouts cortos en las pruebas. |
| El publish autocontenido pesa ~70 MB y la copia por `scp` a la Pi Zero 2 W es lenta. | Aceptable para iterar. Si molesta, `rsync` solo copia lo que cambió; trimming queda para otra spec. |
| `status` justo después de `next` muestra el estado previo porque MPD aún no cambió de pista. | Aceptable en diagnóstico manual; volver a pedir `status`. |
| La fase 1 de la Pi (OS, MPD, DAC) no está lista y bloquea cerrar la spec. | Los criterios de Windows se pueden cumplir antes; la spec queda en `Implemented` solo tras la verificación en la Pi. |

## What is **not** in this spec

- IPC por socket Unix (SPEC 03).
- Unit systemd, usuario `openplayer` y `/opt/openplayer`.
- `initialVolume` / `resumePlaybackOnBoot` al arrancar.
- Conexión persistente, `idle` y publicación de cambios de estado.
- Biblioteca, cola, playlists, búsqueda y escape de argumentos de texto.
- Pantalla de configuración y preferencias editables.
- Contraseña de MPD.
- Cambios en `deploy/`.

Cada uno de estos, si llega, va en su propia spec.
