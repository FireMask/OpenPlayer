# SPEC 01 — Solución .NET 10 y OpenPlayer.Core

> **Status:** Approved
> **Depends on:** —
> **Date:** 2026-10-20
> **Objective:** Crear `OpenPlayer.slnx` con la biblioteca `OpenPlayer.Core` (net10.0) que define modelos, `IPlayer` y la traducción de botones a acciones, probada con xUnit en Windows.

## Scope

**In:**

- `OpenPlayer.slnx` en la raíz del repo.
- `global.json` que fija el SDK `10.0.x` (`rollForward: latestFeature`).
- `Directory.Build.props` con `TargetFramework=net10.0`, `Nullable=enable`, `ImplicitUsings=enable` y `TreatWarningsAsErrors=true`.
- Proyecto `src/OpenPlayer.Core` (classlib, sin dependencias NuGet ni APIs de plataforma).
- Modelos: `Track`, `PlaybackState`, `PlaybackSnapshot`, `PlayerSettings`.
- Contrato `IPlayer`, que incluye `SeekAsync`.
- Enum `ButtonName` con parseo desde los nombres IPC (`play_pause`, `previous`, `next`, `volume_up`, `volume_down`, `menu`).
- `ButtonCommandHandler`, que ejecuta la acción de cada botón sobre `IPlayer`.
- Política de `previous`: si la posición supera `PreviousRestartThreshold`, vuelve a 0; si no, va a la pista anterior.
- Volumen: se recorta a 0–100 en `volume_up`/`volume_down`; con volumen `null` no se hace nada; `SetVolumeAsync` fuera de rango lanza `ArgumentOutOfRangeException`.
- Proyecto `tests/OpenPlayer.Core.Tests` (xUnit) con un `FakePlayer` escrito a mano.
- `dotnet build` y `dotnet test` en verde en Windows.

**Out of scope (para futuras specs):**

- `ILibrary`, `IPlaylistStore`, `IAudioOutputSelector`.
- `OpenPlayer.Mpd` (adaptador del protocolo MPD).
- `OpenPlayer.Service` (host, IPC por socket Unix, carga de `player.example.json`, logging).
- `src/hardware-agent` (Python/GPIO).
- Cambios en `deploy/`, incluido `Requires=` → `Wants=` en `openplayer.service`.
- Publish `linux-arm64` y despliegue en la Pi.
- Pulsación larga, combinaciones y doble clic.
- Acción del botón `menu` (en esta spec no hace nada).

## Data model

Archivos en `src/OpenPlayer.Core/`:

```text
Models/Track.cs
Models/PlaybackState.cs
Models/PlaybackSnapshot.cs
Models/PlayerSettings.cs
Models/Volume.cs                // Volume.EnsureValid(int)
Commands/ButtonName.cs          // enum + ButtonNames.TryParse
Commands/ButtonCommandHandler.cs
Interfaces/IPlayer.cs
```

```csharp
public sealed record Track(
    string Uri,                 // ruta relativa a la biblioteca MPD; dato, nunca comando
    string? Title,
    string? Artist,
    string? Album,
    TimeSpan? Duration);

public enum PlaybackState { Stopped, Playing, Paused }

public sealed record PlaybackSnapshot(
    PlaybackState State,
    Track? CurrentTrack,
    TimeSpan? Position,
    TimeSpan? Duration,
    int? Volume,                // null = sin mixer / desconocido
    DateTimeOffset UpdatedAt);

public sealed record PlayerSettings
{
    public int VolumeStep { get; }                    // 1–100, default 5
    public int InitialVolume { get; }                 // 0–100, default 35
    public TimeSpan PreviousRestartThreshold { get; } // >= 0, default 3 s
    // Constructor valida rangos → ArgumentOutOfRangeException
}

public enum ButtonName { PlayPause, Previous, Next, VolumeUp, VolumeDown, Menu }

public static class ButtonNames
{
    // "play_pause" → PlayPause, etc. Exacto, sensible a mayúsculas. null/desconocido → false.
    public static bool TryParse(string? value, out ButtonName button);
}

public interface IPlayer
{
    Task PlayAsync(CancellationToken ct = default);
    Task PauseAsync(CancellationToken ct = default);
    Task TogglePlaybackAsync(CancellationToken ct = default);
    Task NextAsync(CancellationToken ct = default);
    Task PreviousAsync(CancellationToken ct = default);
    Task SeekAsync(TimeSpan position, CancellationToken ct = default);
    Task SetVolumeAsync(int volume, CancellationToken ct = default); // 0–100
    Task<PlaybackSnapshot> GetSnapshotAsync(CancellationToken ct = default);
}

public sealed class ButtonCommandHandler(IPlayer player, PlayerSettings settings)
{
    public Task HandleAsync(ButtonName button, CancellationToken ct = default);
}
```

Comportamiento de `ButtonCommandHandler.HandleAsync`:

| Botón | Acción |
|---|---|
| `PlayPause` | `TogglePlaybackAsync` |
| `Next` | `NextAsync` |
| `Previous` | Si `Position > PreviousRestartThreshold` → `SeekAsync(TimeSpan.Zero)`; si no, o si `Position` es null → `PreviousAsync` |
| `VolumeUp` | Si `Volume` no es null → `SetVolumeAsync(min(Volume + VolumeStep, 100))`; si es null → nada |
| `VolumeDown` | Igual, con `max(Volume - VolumeStep, 0)` |
| `Menu` | Nada |

Convenciones:

- Posiciones y duraciones en `TimeSpan`.
- Volumen en porcentaje entero, 0–100.
- `IPlayer.SetVolumeAsync` valida el rango en cada implementación. El handler nunca envía valores fuera de rango.
- La validación del rango se centraliza en `Volume.EnsureValid(int)` en Core, para que los adaptadores lo reutilicen.

## Implementation plan

1. Crear `global.json` (SDK `10.0.103`, `rollForward: latestFeature`) y `Directory.Build.props` con las propiedades comunes. Verificar: `dotnet --version` en la raíz devuelve `10.0.x`.
2. Crear `OpenPlayer.slnx`, `src/OpenPlayer.Core` (classlib) y `tests/OpenPlayer.Core.Tests` (xUnit), con la referencia de tests → Core. Quitar `Class1.cs` y la prueba de ejemplo. Verificar: `dotnet build` y `dotnet test` en verde (0 pruebas).
3. Añadir `Models/Volume.cs` (`EnsureValid`) y `Models/PlayerSettings.cs` con validación en el constructor, más sus pruebas de límites (0, 100, −1, 101, paso 0, umbral negativo).
4. Añadir `Track`, `PlaybackState`, `PlaybackSnapshot` e `Interfaces/IPlayer.cs`. Solo tipos, sin pruebas propias. Verificar: compila.
5. Añadir `Commands/ButtonName.cs` con `ButtonNames.TryParse`, más pruebas: los 6 nombres válidos, mayúsculas, vacío, null y desconocido.
6. Añadir `tests/OpenPlayer.Core.Tests/FakePlayer.cs`, que registra las llamadas y devuelve un snapshot configurable.
7. Añadir `Commands/ButtonCommandHandler.cs` con `PlayPause`, `Next` y `Menu`, y sus pruebas.
8. Añadir al handler `Previous` (umbral, igual al umbral, posición null) y sus pruebas.
9. Añadir al handler `VolumeUp`/`VolumeDown` (paso normal, recorte en 0 y 100, volumen null) y sus pruebas.
10. Actualizar `README.md` (comandos `dotnet build`/`dotnet test`) y `docs/architecture.md` §6 (`SeekAsync` en `IPlayer`) y §8 (política de `previous` decidida).

## Acceptance criteria

- [ ] `dotnet --version` en la raíz del repo devuelve `10.0.x`.
- [ ] `dotnet build OpenPlayer.slnx` termina sin errores ni warnings en Windows.
- [ ] `dotnet test OpenPlayer.slnx` pasa todas las pruebas en Windows.
- [ ] `OpenPlayer.Core.csproj` no tiene `PackageReference` ni `RuntimeIdentifier`.
- [ ] Core no usa `System.Net.Sockets`, `System.IO.File`, `System.Diagnostics.Process` ni `Environment` (verificable con grep).
- [ ] `ButtonNames.TryParse` acepta exactamente `play_pause`, `previous`, `next`, `volume_up`, `volume_down` y `menu`, y rechaza cualquier otro valor, incluido `null`.
- [ ] `PlayPause` llama a `TogglePlaybackAsync` una vez y nada más.
- [ ] `Next` llama a `NextAsync` una vez y nada más.
- [ ] `Previous` con posición 5 s y umbral 3 s llama a `SeekAsync(TimeSpan.Zero)` y no llama a `PreviousAsync`.
- [ ] `Previous` con posición 2 s, 3 s o `null` llama a `PreviousAsync` y no llama a `SeekAsync`.
- [ ] `VolumeUp` con volumen 98 y paso 5 llama a `SetVolumeAsync(100)`.
- [ ] `VolumeDown` con volumen 3 y paso 5 llama a `SetVolumeAsync(0)`.
- [ ] `VolumeUp`/`VolumeDown` con volumen `null` no llaman a `SetVolumeAsync`.
- [ ] `Menu` no llama a ningún método de `IPlayer`.
- [ ] `Volume.EnsureValid` lanza `ArgumentOutOfRangeException` con −1 y 101, y acepta 0 y 100.
- [ ] `PlayerSettings` lanza `ArgumentOutOfRangeException` con `VolumeStep` 0 o 101, `InitialVolume` −1 o 101, o un umbral negativo.
- [ ] `docs/architecture.md` §6 incluye `SeekAsync` y §8 documenta la política de `previous`.

## Decisions

- **Sí:** .NET 10 (`net10.0`). Es la LTS vigente y el SDK ya está instalado.
- **Sí:** `global.json` que fija el SDK 10. En la máquina también está el SDK 8; así se evita compilar con la versión equivocada.
- **Sí:** `.slnx`. Es el formato por defecto en .NET 10, en XML legible y con diffs limpios.
- **No:** `.sln` clásico. Formato heredado sin ventaja aquí.
- **Sí:** Core sin RID, como classlib portable. El mismo binario sirve en Windows (pruebas) y en Linux ARM64 (Pi).
- **No:** publish `linux-arm64` en esta spec. Solo aplica al ejecutable (`OpenPlayer.Service`).
- **Sí:** xUnit. Es la plantilla estándar de `dotnet new` y no necesita configuración extra.
- **No:** NUnit/MSTest. No aportan nada para este alcance.
- **Sí:** `FakePlayer` escrito a mano. Evita depender de Moq o NSubstitute para una sola interfaz.
- **Sí:** `TreatWarningsAsErrors` y `Nullable`. Los snapshots tienen muchos campos opcionales y los avisos de null deben bloquear.
- **Sí:** `ButtonCommandHandler` ejecuta la acción sobre `IPlayer`. Así las pruebas cubren el comportamiento real, incluida la política de `previous`.
- **No:** función pura que devuelva un `PlayerCommand`. Añade un tipo intermedio y otro ejecutor sin beneficio actual.
- **Sí:** `SeekAsync(TimeSpan)` en `IPlayer`. Es genérico, MPD lo soporta (`seekcur`) y sirve para reiniciar la pista.
- **No:** `RestartTrackAsync()`. Es demasiado específico.
- **Sí:** `previous` reinicia la pista si `Position > 3 s` y, si no, retrocede. Comportamiento estándar de los reproductores; el umbral es configurable.
- **Sí:** el volumen se recorta a 0–100 en los botones. Pulsar `volume_up` en 98 debe llevar a 100, no fallar.
- **Sí:** `SetVolumeAsync` fuera de rango lanza `ArgumentOutOfRangeException`. Es un error del llamador, no una entrada del usuario.
- **Sí:** volumen `null` = no hacer nada. MPD puede no tener mixer; no se inventa un valor.
- **Sí:** `InitialVolume` en `PlayerSettings` aunque no se use aún. Ya existe en `player.example.json` y lo consumirá el Service.
- **Sí:** el parseo de `ButtonName` es exacto y sensible a mayúsculas. Los nombres son el contrato IPC (`gpio-map.md` §5).
- **No:** cargar la configuración JSON en Core. Core no lee archivos (`architecture.md` §5).

## Risks

| Riesgo | Mitigación |
|---|---|
| Un SDK 10.0.x más nuevo trae analizadores con warnings nuevos que rompen el build por `TreatWarningsAsErrors`. | Corregir el warning o, si no aplica, suprimirlo con `NoWarn` en `Directory.Build.props` y documentar el motivo. |
| La posición de MPD llega con retraso y `previous` cerca de los 3 s decide distinto de lo que el usuario espera. | Aceptable para el MVP: el umbral es configurable en `PlayerSettings` y se ajusta tras probar en la Pi. |
| Core se acopla a la plataforma por error en specs futuras (sockets, archivos). | El criterio de aceptación con grep se puede repetir en cada spec. |

## What is **not** in this spec

- `ILibrary`, `IPlaylistStore`, `IAudioOutputSelector`.
- `OpenPlayer.Mpd` y `OpenPlayer.Service`.
- Agente Python / GPIO.
- Cambios en `deploy/` (incluido `Requires=` → `Wants=`).
- Publish `linux-arm64` y despliegue en la Pi.
- Pulsación larga, combinaciones y doble clic.
- Acción del botón `menu`.

Cada uno de estos, si llega, va en su propia spec.
