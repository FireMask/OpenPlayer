# SPEC 03 — IPC por socket Unix con JSON Lines

> **Status:** Approved
> **Depends on:** SPEC 02
> **Date:** 2026-10-20
> **Objective:** Reemplazar el bucle stdin del Service por un servidor de socket Unix que recibe `button.pressed` y responde `player.get_snapshot` en JSON Lines, verificable con `socat` en la Pi.

## Scope

**In:**

- Eliminar `ConsoleCommandLoop` (stdin); el Service ya no termina por EOF.
- `IpcMessageParser` en Core (`Messages/`), puro y sin IO. Convierte una línea JSON en:
  - `ButtonPressed(button, sequence?)` para `button.pressed`;
  - `SnapshotRequested` para `player.get_snapshot`;
  - un error de validación.
- Reglas de validación:
  - `type` obligatorio.
  - `button` obligatorio en `button.pressed`, con los nombres exactos de `ButtonNames`.
  - `sequence` opcional (entero) y solo se registra en el log.
  - Los campos extra se ignoran.
- `ErrorMessage` en Core: `{"type":"error","request":…,"message":…}`.
- `IpcServer` (`BackgroundService` en el Service), sobre el socket Unix de `ipc.unixSocketPath`.
  - **Al arrancar:** si el directorio no existe, exit 1 con un mensaje claro. Si queda un archivo de socket viejo, se borra. Tras el bind, permisos `0660`.
  - **Clientes:** varios a la vez. Cada uno se lee línea por línea en UTF-8 y soporta mensajes partidos entre lecturas y varios mensajes en un mismo bloque.
  - **Ejecución:** todos los comandos, de cualquier cliente, pasan en serie por un lock global.
  - **`button.pressed`:** ejecuta `ButtonCommandHandler` y no responde nada.
  - **`player.get_snapshot`:** responde un `player.snapshot` solo a ese cliente. Si MPD falla, responde `error` y registra un warning.
  - **Mensaje inválido:** JSON malformado, `type` desconocido o botón inválido registran un warning, y la conexión sigue abierta.
  - **Línea de más de `ipc.maxMessageBytes`:** se registra un warning y se cierra esa conexión.
  - **Al apagar (Ctrl+C o SIGTERM):** deja de aceptar conexiones, cierra los clientes y borra el archivo del socket.
- Validación de la sección `ipc` en `player.json`: `unixSocketPath` no vacío y `maxMessageBytes` entre 256 y 65536. Si falla, exit 1.
- Proyecto `tests/OpenPlayer.Service.Tests` (xUnit) que prueba `IpcServer` con un socket real en una carpeta temporal, sobre Windows.
- Pruebas de `IpcMessageParser` y `ErrorMessage` en `OpenPlayer.Core.Tests`.
- Documentación:
  - `architecture.md`: §7 con el contrato final y, en §10, `ipc.*` como "Usado".
  - README: la prueba con `socat` reemplaza la sección de stdin.
  - `assembly.md`: instalar `socat` y crear `/run/openplayer` a mano.

**Out of scope (para futuras specs):**

- Unit systemd, `RuntimeDirectory`, grupo dedicado, usuario `openplayer` y `/opt/openplayer`.
- Enviar el snapshot a todos los clientes o suscribirse a cambios (OLED).
- El agente Python y los GPIO.
- Acknowledgements de `button.pressed` y deduplicación por `sequence`.
- Pulsaciones largas y combinaciones.
- Aplicar `initialVolume` y `resumePlaybackOnBoot` al arrancar.
- Autenticación por socket (los permisos del archivo bastan).
- Un default de ruta distinto en Windows.

## Data model

Archivos:

```text
src/OpenPlayer.Core/Messages/
  IpcMessage.cs           // IpcMessage, ButtonPressed, SnapshotRequested + IpcMessageParser
  ErrorMessage.cs         // → {"type":"error","request":…,"message":…}
src/OpenPlayer.Service/
  IpcServer.cs            // BackgroundService: socket Unix, framing, despacho, lock global
  PlayerConfig.cs         // + IpcSection (unixSocketPath, maxMessageBytes) → IpcOptions
  Program.cs              // registra IpcServer en lugar de ConsoleCommandLoop
  ConsoleCommandLoop.cs   // se elimina
tests/OpenPlayer.Core.Tests/
  IpcMessageParserTests.cs
  ErrorMessageTests.cs
tests/OpenPlayer.Service.Tests/
  OpenPlayer.Service.Tests.csproj  // xUnit → Service; enlaza FakePlayer.cs de Core.Tests
  IpcServerTests.cs                // socket real en carpeta temporal
```

```csharp
// Core/Messages
public abstract record IpcMessage;
public sealed record ButtonPressed(ButtonName Button, long? Sequence) : IpcMessage;
public sealed record SnapshotRequested : IpcMessage;

public static class IpcMessageParser
{
    // true + message, o false + error legible para el log. Nunca lanza.
    public static bool TryParse(string line, out IpcMessage? message, out string? error);
}

public static class ErrorMessage
{
    public static string Serialize(string request, string message);
}

// Service
public sealed record IpcOptions(string SocketPath, int MaxMessageBytes);
// SocketPath no vacío; MaxMessageBytes 256–65536 → si no, ArgumentException

public sealed class IpcServer(
    IpcOptions options, IPlayer player, ButtonCommandHandler buttons,
    ILogger<IpcServer> logger) : BackgroundService;
```

Mensajes de entrada (una línea UTF-8 terminada en `\n`):

```json
{"type":"button.pressed","button":"next","sequence":1}
{"type":"player.get_snapshot"}
```

Respuestas, solo a `player.get_snapshot` y solo a ese cliente:

```json
{"type":"player.snapshot","state":"playing","trackTitle":"…","trackArtist":"…","positionSeconds":42,"durationSeconds":210,"volume":35}
{"type":"error","request":"player.get_snapshot","message":"MPD did not respond within 3000 ms"}
```

Validación de `IpcMessageParser`:

| Entrada | Resultado |
|---|---|
| JSON inválido o que no es objeto | error `invalid JSON` |
| sin `type`, o `type` no string | error `missing type` |
| `type` desconocido | error `unknown type '<t>'` |
| `button.pressed` sin `button` o con nombre no válido | error `invalid button '<b>'` |
| `sequence` presente y no entero | error `invalid sequence` |
| campos extra | se ignoran |

Framing en `IpcServer`:

- Se leen bytes y se parte por `\n`; un `\r` final se descarta.
- Una línea vacía se ignora.
- El límite se mide en bytes, sin contar el `\n`.
- Si se acumulan más de `MaxMessageBytes` bytes sin `\n`, se registra un warning y se cierra la conexión.

`player.json`, sección `ipc` (ya existe, pasa a usarse):

```json
"ipc": { "unixSocketPath": "/run/openplayer/hardware.sock", "maxMessageBytes": 4096 }
```

## Implementation plan

1. Añadir `IpcMessage.cs` (records + `IpcMessageParser`) en Core, con pruebas en `OpenPlayer.Core.Tests`. Cubrir: `button.pressed` con y sin `sequence`, `player.get_snapshot`, cada fila de la tabla de validación, campos extra ignorados, UTF-8 con acentos.
2. Añadir `ErrorMessage.cs` en Core, con pruebas de JSON exacto (comillas y acentos sin escapar, igual que `SnapshotMessage`).
3. Añadir `IpcSection` → `IpcOptions` en `PlayerConfig`, con validación. En `Program.cs`, validar `ipc` al arrancar: valores inválidos o directorio inexistente → exit 1 con un mensaje que nombra el campo o la ruta. Todavía sin servidor. Verificar a mano: `maxMessageBytes: 10` → exit 1; ruta en un directorio inexistente → exit 1.
4. Crear `tests/OpenPlayer.Service.Tests` (xUnit → Service, enlazando `FakePlayer.cs`) y añadirlo a `OpenPlayer.slnx`. Añadir `IpcServer`:
   - bind con borrado del socket viejo y `chmod 0660`, solo en Linux;
   - una tarea por cliente, con framing por bytes y límite;
   - despacho bajo el lock global;
   - respuesta a `player.get_snapshot`;
   - cierre ordenado que borra el socket.

   Pruebas con un socket real en una carpeta temporal:
   - `button.pressed` → la llamada esperada en `FakePlayer`;
   - `player.get_snapshot` → `player.snapshot`;
   - el `IPlayer` lanza `MpdUnavailableException` → respuesta `error`;
   - mensaje partido en dos escrituras;
   - dos mensajes en una escritura;
   - JSON inválido → la conexión sigue y el siguiente mensaje funciona;
   - línea que excede el límite → conexión cerrada;
   - dos clientes a la vez;
   - socket viejo existente → arranca igual;
   - al detenerse, el archivo del socket desaparece.

   Si `FakePlayer` no permite que `GetSnapshotAsync` lance, se le agrega una propiedad mínima para la prueba de `error`.
5. En `Program.cs`, registrar `IpcServer` y eliminar `ConsoleCommandLoop.cs`. Verificar a mano en Windows, con `player.json` apuntando a una carpeta temporal: arranca, queda escuchando y Ctrl+C sale con 0 y borra el socket.
6. Actualizar la documentación:
   - `architecture.md` §7: mensajes, respuestas, errores y framing;
   - `architecture.md` §10: `ipc.*` pasa a "Usado";
   - README: la prueba con `socat` reemplaza "Ejecutar el Service";
   - `assembly.md` §7: `sudo apt install socat` y `sudo mkdir -p /run/openplayer && sudo chown $USER /run/openplayer`, con la nota de que se pierde al reiniciar.
7. Publicar con `deploy.ps1` y verificar en la Pi con `socat` (criterios manuales).

## Acceptance criteria

**Windows (automatizable):**

- [ ] `dotnet build OpenPlayer.slnx` termina sin errores ni warnings.
- [ ] `dotnet test OpenPlayer.slnx` pasa todas las pruebas (Core, Mpd y Service).
- [ ] Core sigue sin `PackageReference` ni `Microsoft.Extensions.*`.
- [ ] `IpcMessageParser` acepta `button.pressed` (con y sin `sequence`) y `player.get_snapshot`, ignora campos extra y rechaza cada caso de la tabla de validación sin lanzar.
- [ ] `ErrorMessage` produce exactamente `{"type":"error","request":…,"message":…}`.
- [ ] `IpcServer`: `button.pressed` ejecuta el botón en el `IPlayer`, y `player.get_snapshot` responde una línea `player.snapshot` solo a ese cliente.
- [ ] `IpcServer`: si `GetSnapshotAsync` lanza `MpdUnavailableException`, responde `error` y la conexión sigue abierta.
- [ ] `IpcServer`: un mensaje partido en dos escrituras y dos mensajes en una sola escritura se procesan correctamente.
- [ ] `IpcServer`: después de un JSON inválido, el siguiente mensaje válido de la misma conexión se procesa.
- [ ] `IpcServer`: una línea de más de `maxMessageBytes` cierra esa conexión, y otros clientes siguen funcionando.
- [ ] `IpcServer`: dos clientes conectados a la vez reciben cada uno su propia respuesta.
- [ ] `IpcServer`: arranca aunque exista un archivo de socket viejo, y al detenerse borra el archivo.
- [ ] `ConsoleCommandLoop.cs` ya no existe.
- [ ] Con `ipc.maxMessageBytes: 10`, o con `unixSocketPath` en un directorio inexistente, el Service sale con exit code 1 y un mensaje que nombra el campo o la ruta.

**Raspberry Pi (manual por SSH; requiere `socat` y `/run/openplayer` creado a mano):**

- [ ] `deploy.ps1` publica y el Service arranca escuchando en `/run/openplayer/hardware.sock`.
- [ ] `ls -l` muestra el socket con permisos `srw-rw----`.
- [ ] `echo '{"type":"player.get_snapshot"}' | socat - UNIX-CONNECT:/run/openplayer/hardware.sock` imprime un `player.snapshot` que coincide con `mpc current`.
- [ ] `{"type":"button.pressed","button":"play_pause"}` alterna la reproducción según `mpc status`.
- [ ] `next`, `previous`, `volume_up` y `volume_down` por socket producen el mismo efecto que en la SPEC 02.
- [ ] `{"type":"button.pressed","button":"foo"}` y una línea `hola` registran un warning, y el Service sigue funcionando.
- [ ] Con MPD detenido (`sudo systemctl stop mpd`), `player.get_snapshot` responde `{"type":"error",…}`; al volver a arrancar MPD, la siguiente consulta funciona.
- [ ] Ctrl+C detiene el Service con exit code 0 y el archivo del socket desaparece.
- [ ] El Service corriendo con stdin cerrado (`< /dev/null`) no termina: sigue atendiendo el socket.

**Documentación:**

- [ ] `docs/architecture.md` §7 documenta los mensajes, las respuestas, los errores y el framing; §10 marca `ipc.*` como "Usado".
- [ ] `README.md` explica cómo probar con `socat` y ya no menciona stdin.
- [ ] `docs/assembly.md` incluye la instalación de `socat` y la creación temporal de `/run/openplayer`.

## Decisions

- **Sí:** eliminar el bucle stdin. Bajo systemd, stdin es `/dev/null`, y el EOF apagaría el Service. `socat` prueba el contrato real.
- **No:** flag `--console` o stdin junto al socket. Son dos entradas que mantener para algo que `socat` ya cubre.
- **Sí:** `player.get_snapshot`, que responde solo al cliente que la pide. Reemplaza al `status` de stdin, y la OLED lo va a necesitar.
- **No:** enviar el snapshot a todos los clientes o suscribirse a cambios. Requiere `idle` o polling a MPD; va en la spec de OLED.
- **No:** acknowledgements de `button.pressed`. Para el MVP bastan el log y el estado de MPD (`architecture.md` §7).
- **Sí:** responder `error` cuando falla una consulta. Sin respuesta, el cliente no sabe si debe seguir esperando.
- **Sí:** ignorar los campos extra. Permite añadir campos, por ejemplo `timestamp`, sin romper un Service anterior.
- **Sí:** `sequence` opcional y solo registrado en el log. La deduplicación se añade si las pruebas con botones reales muestran duplicados.
- **Sí:** un mensaje inválido no cierra la conexión. Un bug en el agente no debe dejar los botones muertos (`architecture.md` §7: no terminar por un evento malformado).
- **Sí:** una línea que excede el límite cierra la conexión. Después de truncar no se puede saber dónde empieza el siguiente mensaje; el agente reconecta.
- **Sí:** límite medido en bytes, no en caracteres. Es lo que cuesta memoria, y protege igual con texto UTF-8 de varios bytes.
- **Sí:** varios clientes, con un lock global para los comandos. Permite agente y `socat` a la vez; el lock evita que dos `volume_up` simultáneos lean el mismo volumen y pierdan un paso.
- **Sí:** borrar el socket viejo al arrancar. Tras una caída queda el archivo, y el bind fallaría.
- **Sí:** `0660` después del bind. El dueño y el grupo pueden conectarse y otros usuarios no; el grupo dedicado llega con systemd.
- **Sí:** exit 1 si el directorio del socket no existe. Crear `/run/openplayer` es responsabilidad de systemd (`RuntimeDirectory`); el Service no debe necesitar root.
- **No:** usar `/tmp` o `$HOME` como ruta por defecto. `architecture.md` §7 descarta `/tmp` como ruta de confianza.
- **Sí:** `IpcMessageParser` en Core. Es lógica pura, se prueba sin sockets, y el agente Python tendrá el contrato documentado en §7.
- **Sí:** `IpcServer` en el Service, con su propio proyecto de pruebas. Un proyecto `OpenPlayer.Ipc` aparte no aporta nada mientras haya un solo consumidor.
- **Sí:** pruebas con un socket Unix real en Windows. .NET lo soporta en Windows 10+, y prueba el framing de verdad sin la Pi.
- **Sí:** reutilizar `FakePlayer` de Core.Tests enlazando el archivo. Evita un segundo fake que se desincronice.

## Risks

| Riesgo | Mitigación |
|---|---|
| `/run/openplayer` creado a mano se pierde al reiniciar la Pi. | Aceptado hasta la spec de systemd (`RuntimeDirectory`). El Service sale con exit 1 y un mensaje claro que lo indica. |
| Los sockets Unix en Windows tienen diferencias (no hay permisos `chmod`, rutas con `\`). | `chmod` se aplica solo en Linux. Los permisos se verifican en la Pi, no en las pruebas de Windows. |
| Pruebas de socket inestables por timing (cierre, varios clientes). | Timeouts cortos con `CancellationTokenSource` en cada prueba. Las aserciones esperan respuestas, no sleeps. |
| Un cliente lento o colgado bloquea a otros mientras tiene el lock. | El lock solo cubre la ejecución del comando, no la lectura ni la escritura. Las operaciones MPD ya tienen timeout (`connectTimeoutMs`). |
| `socat` envía EOF justo después de enviar, y el Service podría cerrar antes de responder. | Se procesa la línea completa antes de cerrar por EOF. Si `socat` corta la respuesta, se usa `socat -t 2` y se documenta en el README. |
| Dos instancias del Service compiten por el mismo socket: la segunda borra el de la primera. | Aceptado para desarrollo manual. systemd garantiza una sola instancia; no se añade un lockfile (YAGNI). |

## What is **not** in this spec

- Unit systemd, `RuntimeDirectory`, grupo dedicado, usuario `openplayer` y `/opt/openplayer`.
- Enviar el snapshot a todos los clientes o suscribirse a cambios.
- Agente Python y GPIO.
- Acknowledgements y deduplicación por `sequence`.
- Pulsaciones largas y combinaciones.
- `initialVolume` / `resumePlaybackOnBoot` al arrancar.
- Autenticación por socket.

Cada uno de estos, si llega, va en su propia spec.
