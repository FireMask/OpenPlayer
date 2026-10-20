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

    Task<PlaybackSnapshot> GetSnapshotAsync(CancellationToken ct = default);
}
