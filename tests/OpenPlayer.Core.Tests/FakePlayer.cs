using OpenPlayer.Core.Interfaces;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Tests;

/// <summary>Registra cada llamada (incluida GetSnapshot) y devuelve <see cref="Snapshot"/>, o lanza <see cref="SnapshotError"/>.</summary>
internal sealed class FakePlayer : IPlayer
{
    public List<string> Calls { get; } = [];

    public PlaybackSnapshot Snapshot { get; set; } =
        new(PlaybackState.Stopped, null, null, null, null, DateTimeOffset.UnixEpoch);

    public Exception? SnapshotError { get; set; }

    public Exception? SeekError { get; set; }

    public static PlaybackSnapshot SnapshotWith(TimeSpan? position = null, int? volume = null) =>
        new(PlaybackState.Playing, null, position, null, volume, DateTimeOffset.UnixEpoch);

    public Task PlayAsync(CancellationToken ct = default) => Record("Play");
    public Task PauseAsync(CancellationToken ct = default) => Record("Pause");
    public Task TogglePlaybackAsync(CancellationToken ct = default) => Record("TogglePlayback");
    public Task NextAsync(CancellationToken ct = default) => Record("Next");
    public Task PreviousAsync(CancellationToken ct = default) => Record("Previous");
    public Task SeekAsync(TimeSpan position, CancellationToken ct = default)
    {
        Calls.Add($"Seek({position})");
        return SeekError is { } e ? Task.FromException(e) : Task.CompletedTask;
    }

    public Task UpdateLibraryAsync(CancellationToken ct = default) => Record("UpdateLibrary");

    public Task SetVolumeAsync(int volume, CancellationToken ct = default) =>
        Record($"SetVolume({Volume.EnsureValid(volume)})");

    public Task<PlaybackSnapshot> GetSnapshotAsync(CancellationToken ct = default)
    {
        Calls.Add("GetSnapshot");
        return SnapshotError is { } e ? Task.FromException<PlaybackSnapshot>(e) : Task.FromResult(Snapshot);
    }

    // Sin cambios: espera hasta que se cancele. No se registra en Calls.
    public Task WaitForChangeAsync(CancellationToken ct = default) => Task.Delay(Timeout.Infinite, ct);

    private Task Record(string call)
    {
        Calls.Add(call);
        return Task.CompletedTask;
    }
}
