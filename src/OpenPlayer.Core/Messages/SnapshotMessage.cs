using System.Text.Encodings.Web;
using System.Text.Json;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Messages;

/// <summary>Mensaje IPC <c>player.snapshot</c> (architecture.md §7): una línea JSON.</summary>
public static class SnapshotMessage
{
    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        // Acentos legibles por SSH; el mensaje nunca se incrusta en HTML.
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    public static string Serialize(PlaybackSnapshot snapshot) => JsonSerializer.Serialize(
        new Payload(
            "player.snapshot",
            snapshot.State switch
            {
                PlaybackState.Playing => "playing",
                PlaybackState.Paused => "paused",
                _ => "stopped",
            },
            snapshot.CurrentTrack?.Title,
            snapshot.CurrentTrack?.Artist,
            WholeSeconds(snapshot.Position),
            WholeSeconds(snapshot.Duration),
            snapshot.Volume),
        Options);

    private static long? WholeSeconds(TimeSpan? value) => value is { } v ? (long)v.TotalSeconds : null;

    private sealed record Payload(
        string Type,
        string State,
        string? TrackTitle,
        string? TrackArtist,
        long? PositionSeconds,
        long? DurationSeconds,
        int? Volume);
}
