namespace OpenPlayer.Core.Models;

/// <param name="Volume">0–100, o null si no hay mixer o es desconocido.</param>
public sealed record PlaybackSnapshot(
    PlaybackState State,
    Track? CurrentTrack,
    TimeSpan? Position,
    TimeSpan? Duration,
    int? Volume,
    DateTimeOffset UpdatedAt);
