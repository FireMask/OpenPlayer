using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Interfaces;

public interface IPlayer
{
    Task PlayAsync(CancellationToken ct = default);
    Task PauseAsync(CancellationToken ct = default);
    Task TogglePlaybackAsync(CancellationToken ct = default);
    Task NextAsync(CancellationToken ct = default);
    Task PreviousAsync(CancellationToken ct = default);
    Task SeekAsync(TimeSpan position, CancellationToken ct = default);

    /// <summary>Volumen 0–100. Las implementaciones validan con <see cref="Volume.EnsureValid"/>.</summary>
    Task SetVolumeAsync(int volume, CancellationToken ct = default);

    /// <summary>Reescanea la biblioteca de música en segundo plano.</summary>
    Task UpdateLibraryAsync(CancellationToken ct = default);

    Task<PlaybackSnapshot> GetSnapshotAsync(CancellationToken ct = default);

    /// <summary>Carátula de la pista actual (SPEC 19). Lanza <see cref="CoverTooLargeException"/> si pasa de <see cref="Cover.MaxBytes"/>.</summary>
    Task<Cover> GetCoverAsync(CancellationToken ct = default);

    /// <summary>Espera hasta que cambie el reproductor, el volumen, la cola o las opciones. MPD: <c>idle player mixer playlist options</c>.</summary>
    Task WaitForChangeAsync(CancellationToken ct = default);
}
