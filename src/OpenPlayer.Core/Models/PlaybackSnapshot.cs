namespace OpenPlayer.Core.Models;

/// <param name="Volume">0–100, o null si no hay mixer o es desconocido.</param>
/// <param name="QueuePosition">Índice 0-based de la pista actual en la cola (MPD <c>status: song</c>).</param>
/// <param name="QueueVersion">Versión de la cola (MPD <c>status: playlist</c>); cambia con cada edición.</param>
public sealed record PlaybackSnapshot(
    PlaybackState State,
    Track? CurrentTrack,
    TimeSpan? Position,
    TimeSpan? Duration,
    int? Volume,
    DateTimeOffset UpdatedAt,
    int? QueuePosition = null,
    long? QueueVersion = null);
