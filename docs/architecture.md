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
[Cliente remoto futuro] -------------------------- API local futura -----+       +--> [OpenPlayer.Core]
                                                                                 |
                                                                                 +--> [OpenPlayer.Mpd] --> [MPD]
                                                                                                      |
                                                                                          [ALSA / PipeWire]
                                                                                           /           \
                                                                                     [DAC USB]    [Bluetooth A2DP]
```

SSH es un canal de administración; no implica que la aplicación deba aceptar comandos shell desde la red. La API HTTP es futura, no un requisito del MVP.

## 5. Componentes y responsabilidades

### `OpenPlayer.Core`

Biblioteca .NET sin dependencias de plataforma ni paquetes MPD. Contiene:

- Modelos: `Track`, `Playlist`, `PlaybackSnapshot`, `PlayerSettings`.
- Contratos: `IPlayer`, `ILibrary`, `IPlaylistStore`, `IAudioOutputSelector` (este último puede esperar a la fase Bluetooth).
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
- Más adelante puede hospedar una API HTTP local autenticada.

### `src/hardware-agent`

Proceso Python:

- Configura botones GPIO con pull-up y debounce.
- Envía eventos JSON Lines al socket Unix.
- Maneja reconexión si el servicio aún no está disponible.
- En la fase OLED, dibuja el estado recibido o consultado por un canal definido; no consulta MPD directamente.
- Debe permitir simulación o pruebas sin hardware real.

### MPD y salida de audio

MPD administra la biblioteca, la cola y la reproducción. Para el primer hito, seleccionar el DAC USB mediante ALSA. No codificar un índice de tarjeta fijo: inspeccionar `aplay -l` y `/proc/asound/cards`. Bluetooth A2DP puede requerir PipeWire/WirePlumber o una configuración equivalente de la distribución. Validar la ruta de audio en el sistema operativo elegido antes de implementar un selector automático.

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
    Task SetVolumeAsync(int volume, CancellationToken ct = default);
    Task<PlaybackSnapshot> GetSnapshotAsync(CancellationToken ct = default);
}
```

`PlaybackSnapshot` debe incluir como mínimo estado, pista actual nullable, posición, duración, volumen y timestamp de actualización. Usar `TimeSpan` para posiciones/duraciones. No asumir que todos los metadatos existen.

`ILibrary` debe ofrecer búsquedas acotadas y paginables cuando sea posible. `IPlaylistStore` puede delegar inicialmente todas las listas persistentes a MPD; no crear una segunda copia de la cola sin una necesidad concreta.

## 7. IPC Python ↔ C#

Transporte inicial: Unix domain socket local, ruta propuesta `/run/openplayer/hardware.sock`. El directorio `/run/openplayer` debe crearse en el arranque mediante `systemd` (`RuntimeDirectory=openplayer`) y asignarse a un grupo dedicado. No usar `/tmp` como ruta de confianza a largo plazo.

Formato: un objeto JSON por línea UTF-8, con límite de tamaño, por ejemplo 4 KiB por mensaje.

Evento de entrada:

```json
{"type":"button.pressed","button":"next","sequence":1}
```

Respuesta/estado futuro:

```json
{"type":"player.snapshot","state":"playing","trackTitle":"Example","positionSeconds":42,"durationSeconds":210,"volume":35}
```

Reglas:

- El servidor lee hasta newline; una llamada `recv` no garantiza recibir un mensaje completo.
- Validar JSON, `type`, nombre de botón y tamaño máximo.
- No aceptar comandos arbitrarios ni nombres de ejecutables por IPC.
- Ignorar o registrar tipos desconocidos; no terminar el proceso por un evento malformado.
- Definir si se requieren acknowledgements; para el MVP, log de recepción y estado MPD son suficientes.
- Reconectar con espera incremental limitada; no registrar cada intento en un bucle rápido.
- Añadir identificadores/sequence si se detectan eventos duplicados en pruebas.

## 8. Mapeo de botones

- `play_pause`: alterna reproducción/pausa.
- `previous`: pista anterior; decidir y documentar si una pulsación dentro de los primeros segundos reinicia la pista o siempre retrocede.
- `next`: siguiente pista.
- `volume_up` / `volume_down`: cambiar volumen en pasos configurables, por ejemplo 5 puntos porcentuales.
- `menu`: reservado para navegación OLED futura; en el MVP puede no hacer nada o generar un evento registrado.

Las pulsaciones largas, combinaciones y doble clic son posteriores al MVP. Evitar que una misma pulsación genere tanto una acción corta como una larga.

## 9. Biblioteca, cola y listas

En v1, usar la base de biblioteca y las playlists de MPD. Implementar:

- Listado de pistas y búsqueda por texto.
- Estado de la cola y pista actual.
- Añadir pista a cola y limpiar cola con confirmación en interfaces futuras.
- Crear/listar/guardar playlists mediante el protocolo MPD.
- Tratar los URI/rutas como datos, nunca como shell commands.

Una base SQLite propia queda pospuesta para preferencias, historial de reproducción, ratings o datos que MPD no cubra.

## 10. Configuración

Archivo propuesto `config/player.example.json`. Separar valores de despliegue (rutas, host/puerto MPD, socket) de preferencias (volumen inicial, pasos de volumen, salida preferida). No guardar contraseñas ni claves en el repositorio. Validar configuración al arrancar y mostrar errores accionables.

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

1. Instalar Raspberry Pi OS Lite, SSH, MPD y verificar DAC USB.
2. Crear solución .NET, Core e interfaz `IPlayer`.
3. Implementar adaptador MPD y snapshot de estado.
4. Implementar socket Unix y agente Python con dos botones.
5. Añadir biblioteca y playlists.
6. Instalar servicios systemd y validar arranque automático.
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
