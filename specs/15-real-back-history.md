# SPEC 15 — Historial real para ⏮

> **Status:** Approved
> **Depends on:** SPEC 02, SPEC 03, SPEC 14
> **Date:** 2026-10-22
> **Objective:** Que el Service observe los cambios de canción de MPD (`idle player`), recuerde las últimas 50 canciones escuchadas y que ⏮ (a ≤ 3 s) devuelva la anterior arriba de la cola y la reproduzca.

## Scope

**In:**

- Core:
  - `PlaybackSnapshot.SongId` (`int?`, MPD `songid`).
  - `IPlayer.WaitForChangeAsync()`: espera hasta que cambie el estado del reproductor.
- Mpd:
  - `MpdClient.IdleAsync`: conexión propia, `idle player`, sin timeout después del saludo (el timeout de conexión sigue).
  - `MpdPlayer.WaitForChangeAsync` lo usa; `MpdSnapshotParser` lee `songid`.
  - `IQueue.RestoreAsync(string uri)`: `add "<uri>" 0` + `play 0` en una conexión.
- Service (`IpcServer`):
  - Historial en memoria: últimas 50 entradas `(uri, origen)`, como pila; se pierde al reiniciar; sobrevive a `queue.clear`, `playlist.play` y `library.play`.
  - Observador en segundo plano (junto a `EnableConsumeAsync`): `WaitForChangeAsync` → snapshot bajo el lock → si `SongId` cambió y la anterior estaba en `play` o `pause`, entra al historial con su etiqueta de `_sources`. Si MPD no responde: warning y reintento a los 5 s.
  - ⏮ (`button.pressed previous`, web y botón físico): si posición ≤ `PreviousRestartThreshold` y hay historial → saca la última, `RestoreAsync`, etiqueta el id nuevo con su origen y marca esa canción como la actual (el cambio no entra al historial). Si no, `ButtonCommandHandler` como hoy.
  - Si `RestoreAsync` falla con ACK (archivo borrado): descarta la entrada, warning, y ⏮ como hoy.
  - Si la medición del paso 1 muestra que MPD borra la canción que estaba sonando al saltar arriba: el Service la vuelve a agregar en la posición 1 con su etiqueta.
- Pruebas: Core (snapshot), Mpd (`idle`, `songid`, comandos exactos de `RestoreAsync`), Service (historial, ⏮ con y sin historial, umbral, pila ⏮⏮, tope 50, canción no reproducida no entra, ACK, MPD caído).
- Docs: `architecture.md` §6, §7, §9; README (⏮ vuelve a la anterior).

**Out of scope (for future specs):**

- Actualización instantánea (IPC push + SSE + página): reutilizará el observador.
- Sección "Escuchadas recientemente" en la web.
- Persistir el historial entre reinicios del Service.
- Recuperar cambios perdidos entre dos despertares de `idle` (milisegundos).
- Probar la entrada siguiente si la restaurada ya no existe.
- Spotify-style, arrastrar para reordenar, agregar a la cola desde Listas.

## Data model

**Core:**

```csharp
public sealed record PlaybackSnapshot(
    PlaybackState State, Track? CurrentTrack, TimeSpan? Position, TimeSpan? Duration,
    int? Volume, DateTimeOffset UpdatedAt,
    int? QueuePosition = null, long? QueueVersion = null,
    int? SongId = null);                 // nuevo: MPD songid

// IPlayer
Task WaitForChangeAsync(CancellationToken ct = default);   // MPD: idle player

// IQueue
Task RestoreAsync(string uri, CancellationToken ct = default);   // add "<uri>" 0 + play 0
```

**Service (`IpcServer`, en memoria, bajo `_commandLock`):**

```csharp
private sealed record PlayedSong(string Uri, string? Source);
private sealed record CurrentSong(int Id, string Uri, bool Played);  // Played: estuvo en play o pause

private readonly LinkedList<PlayedSong> _history = [];   // último al final; tope 50 (descarta el más viejo)
private CurrentSong? _current;
private const int HistoryLimit = 50;
```

| MPD | Comando |
|---|---|
| `MpdClient.IdleAsync` | `idle player` (espera `changed: player` + `OK`) |
| `MpdPlayer.WaitForChangeAsync` | `IdleAsync` |
| `MpdQueue.RestoreAsync` | `add "<uri>" 0`, `play 0` (una conexión) |
| Paso 1 → re-agregar (si hace falta) | `add "<uri>" 1` |

No cambia el protocolo IPC ni `player.json` (el tope 50 y los 5 s de reintento son constantes).

## Implementation plan

1. **Medición en la Pi (sin código).**
   - Con `consume: on`, reproducir una lista de 3+ canciones y dejar sonar la primera unos segundos.
   - `printf 'add "<uri de otra canción>" 0\nplay 0\nclose\n' | nc localhost 6600`, luego `mpc playlist` y `mpc status`.
   - Anotar si la canción que sonaba sigue en la posición 2 o MPD la borró. El resultado decide si el Service la re-agrega (`add "<uri>" 1`); se anota en Decisiones.
2. **Core + Mpd: `SongId`.**
   - `PlaybackSnapshot.SongId`; `MpdSnapshotParser` lee `songid` (entero no negativo, si no `null`).
   - Pruebas de parser.
3. **Mpd: `idle`.**
   - `MpdClient.IdleAsync` (conexión propia, sin timeout tras el saludo, cancelable).
   - `IPlayer.WaitForChangeAsync` + `MpdPlayer`; los fakes de pruebas lo implementan.
   - Pruebas con `FakeMpdServer`: envía `idle player`, vuelve al recibir `changed: player` + `OK`, cancelación cierra la conexión.
4. **Mpd: `RestoreAsync`.**
   - `IQueue.RestoreAsync` + `MpdQueue` (`add "<uri>" 0`, `play 0`), `FakeLibrary`.
   - Pruebas de comandos exactos y ACK.
5. **Service: observador e historial.**
   - Tarea de fondo en `ExecuteAsync` junto a `EnableConsumeAsync`: `WaitForChangeAsync` → snapshot bajo el lock → actualiza `_current` y `_history` (tope 50, solo canciones `Played`). MPD caído: warning, reintento a los 5 s.
   - Pruebas: cambio de canción entra al historial con su etiqueta; no reproducida no entra; tope 50; MPD caído no detiene el Service.
6. **Service: ⏮.**
   - `button.pressed previous`: posición ≤ umbral y historial no vacío → saca la última, `RestoreAsync`, etiqueta el id nuevo, `_current` = la restaurada; re-agrega la anterior si el paso 1 lo pide. Si no, `ButtonCommandHandler`.
   - ACK de `RestoreAsync`: descarta la entrada, warning, `ButtonCommandHandler`.
   - Pruebas: con/sin historial, sobre el umbral, ⏮⏮ (pila, sin rebote), ACK.
7. **Docs.**
   - `architecture.md` §6 (`SongId`, `WaitForChangeAsync`, `RestoreAsync`), §7 (observador, historial, ⏮), §9 (hecho: historial; pendiente sigue SSE).
   - README: ⏮ a ≤ 3 s vuelve a la canción anterior; el historial se pierde al reiniciar.

## Acceptance criteria

**Código y pruebas:**

- [ ] `PlaybackSnapshot.SongId` se lee de `songid`; `songid` inválido o ausente → `null`.
- [ ] `MpdClient.IdleAsync` envía `idle player` en su propia conexión, vuelve con `changed: player` + `OK` y se cancela sin quedar colgado.
- [ ] `MpdQueue.RestoreAsync` envía exactamente `add "<uri>" 0` y `play 0` en una conexión.
- [ ] Al cambiar `SongId`, la canción anterior entra al historial con su etiqueta solo si estuvo en `play` o `pause`.
- [ ] El historial guarda como máximo 50 entradas y descarta la más vieja.
- [ ] ⏮ a ≤ umbral con historial llama `RestoreAsync` con la última entrada y la quita; sin historial o sobre el umbral se comporta como antes.
- [ ] La canción restaurada recibe su etiqueta de origen original.
- [ ] ⏮⏮ restaura dos canciones distintas en orden inverso (sin rebote).
- [ ] ACK en `RestoreAsync` descarta la entrada, registra un warning y ⏮ actúa como antes.
- [ ] MPD caído al arrancar o durante `idle`: el Service sigue respondiendo IPC y el observador reintenta.
- [ ] Todas las suites pasan (Core, Mpd, Service, web agent, hardware agent).

**En la Pi:**

- [ ] Paso 1 medido y anotado en Decisiones.
- [ ] Reproducir una lista, dejar terminar una canción (o ⏭), ⏮ antes de 3 s: suena la anterior desde 0:00, arriba de la cola, con su etiqueta.
- [ ] La canción que sonaba queda segunda en la cola.
- [ ] ⏮ pasados 3 s reinicia la canción actual.
- [ ] ⏮ con historial vacío (Service recién reiniciado) reinicia la canción actual.
- [ ] El botón físico ⏮ hace lo mismo que el de la web.

**Docs:**

- [ ] `architecture.md` §6, §7 y §9 describen `SongId`, `WaitForChangeAsync`, `RestoreAsync`, el observador y el historial.
- [ ] README explica que ⏮ a ≤ 3 s vuelve a la anterior y que el historial se pierde al reiniciar.

## Decisions

**Tomadas:**

- **`idle player` para detectar cambios.** Funciona sin la web abierta (botón físico) y avisa también cuando una canción termina sola. El instant-updates futuro reutiliza el mismo observador.
- **Esta spec construye el observador solo para el historial.** IPC push + SSE quedan para su propia spec; así el observador se prueba en la Pi antes.
- **⏮ inserta arriba y la actual baja a segunda** (modelo Spotify), en vez de reemplazarla.
- **Historial como pila; los cambios causados por ⏮ no entran.** Evita que ⏮⏮ rebote entre dos canciones. Al terminar normalmente, la restaurada vuelve a entrar.
- **Memoria, tope 50, se pierde al reiniciar.** Igual que las etiquetas de SPEC 14; sin archivos ni versiones.
- **Guarda la etiqueta de origen** y la reaplica al id nuevo.
- **Sobrevive a `queue.clear`, `playlist.play` y `library.play`.** Lo escuchado sigue siendo escuchado.
- **Solo entran canciones que estuvieron en `play` o `pause`.** Una lista cargada y nunca reproducida no llena el historial.
- **Lógica en `IpcServer`.** Ya tiene `_sources`, el lock global y la tarea de arranque; `ButtonCommandHandler` sigue igual para el resto.
- **Archivo borrado al restaurar → descartar y ⏮ como antes.** Simple; no recorre el historial.
- **Constantes en código (50, 5 s).** No hay pedido de configurarlas.
- **Resultado del paso 1 (MPD 0.24.4, `consume: on`):** con "Favoritas" (7) sonando, `add "Adele/A1 - Rolling In The Deep.flac" 0` + `play 0` dejó la restaurada en `#1/8` sonando y la que sonaba quedó segunda; MPD no la borró. El Service no re-agrega nada (`add "<uri>" 1` no se usa).

**Descartadas:**

- **Temporizador que consulta `status` cada 1 s.** Más simple, pero `idle` es lo correcto y lo reutiliza el SSE.
- **Registrar solo en ⏭ / `queue.play`.** Pierde las canciones que terminan solas.
- **Instant-updates primero.** Spec grande (4 áreas); el historial no la necesita.
- **Reemplazar la actual con ⏮.** Pierde la canción que sonaba.
- **Persistir en JSON.** Sin pedido; suma formato y escritura en disco.
- **Clase nueva en el Service.** Necesitaría compartir lock y etiquetas con `IpcServer`; más código sin beneficio hoy.
- **Sección "Escuchadas recientemente" en la web.** Spec propia.

## Risks

| Riesgo | Mitigación |
|---|---|
| Con `consume`, `play 0` borra la canción que sonaba (ahora en posición 1) | Paso 1 lo mide antes de escribir código; si la borra, el Service la re-agrega en la posición 1 con su etiqueta. |
| El observador y un comando IPC ven el mismo cambio a la vez | El observador lee el snapshot y actualiza `_current`/`_history` bajo `_commandLock`; ⏮ fija `_current` dentro del mismo lock. |
| `idle` queda colgado si MPD se reinicia sin cerrar la conexión | La conexión se cierra al cancelar; un error de socket pasa a reintento a los 5 s. ponytail: sin keepalive; agregar timeout de `idle` si se ve en la Pi. |
| Dos cambios entre despertares de `idle` (A→B→C) | Aceptado: B se pierde del historial (milisegundos). |
| `songid` se reutiliza tras reiniciar MPD | El observador relee el snapshot al reconectar; a lo sumo una entrada de historial incorrecta. |
| Servicio reiniciado: historial vacío | Documentado en README; ⏮ reinicia la actual, como en SPEC 14. |
| Etiqueta de la canción re-agregada (paso 1) | Se copia de `_sources` del id viejo al nuevo antes de borrarlo. |

## What is **not** in this spec

- Actualización instantánea (IPC push + SSE + página).
- Sección "Escuchadas recientemente" en la web.
- Persistir el historial entre reinicios.
- Probar la siguiente entrada si la restaurada no existe.
- Reproducir una lista sin borrar lo agregado (modelo tipo Spotify).
- Arrastrar para reordenar; agregar a la cola desde Listas; OLED.

Cada uno, si llega, va en su propia spec.
