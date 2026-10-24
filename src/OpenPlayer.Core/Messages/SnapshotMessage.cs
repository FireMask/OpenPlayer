using System.Text.Encodings.Web;
using System.Text.Json;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Messages;

/// <summary>Mensaje IPC <c>player.snapshot</c> (architecture.md §7): una línea JSON.</summary>
public static class SnapshotMessage
{
    internal static readonly JsonSerializerOptions Options = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        // Acentos legibles por SSH; el mensaje nunca se incrusta en HTML.
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    /// <param name="displayMode">Modo de la pantalla redonda (SPEC 18): "track" o "clock"; no viene de MPD.</param>
    public static string Serialize(PlaybackSnapshot snapshot, string displayMode = "track") => JsonSerializer.Serialize(
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
            snapshot.CurrentTrack?.Album,
            WholeSeconds(snapshot.Position),
            WholeSeconds(snapshot.Duration),
            snapshot.Volume,
            snapshot.QueuePosition,
            snapshot.QueueLength,
            snapshot.QueueVersion,
            displayMode),
        Options);

    private static long? WholeSeconds(TimeSpan? value) => value is { } v ? (long)v.TotalSeconds : null;

    private sealed record Payload(
        string Type,
        string State,
        string? TrackTitle,
        string? TrackArtist,
        string? TrackAlbum,
        long? PositionSeconds,
        long? DurationSeconds,
        int? Volume,
        int? QueuePosition,
        int? QueueLength,
        long? QueueVersion,
        string DisplayMode);
}
