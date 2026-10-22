using System.Text.Json;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Messages;

/// <summary>Respuesta IPC <c>queue.page</c> (SPEC 11): pistas como en <c>library.page</c>, sin <c>directory</c>.</summary>
public static class QueuePageMessage
{
    public static string Serialize(LibraryPage page, string? playlist) => JsonSerializer.Serialize(
        new Payload(
            "queue.page",
            playlist,
            page.Offset,
            page.Total,
            [.. page.Entries.Select(e => new Entry(e.Uri, e.Track?.Title, e.Track?.Artist, e.Track?.Album,
                e.Track?.Duration is { } d ? (long)d.TotalSeconds : null))]),
        SnapshotMessage.Options);

    private sealed record Payload(string Type, string? Playlist, int Offset, int Total, IReadOnlyList<Entry> Entries);

    private sealed record Entry(string Uri, string? Title, string? Artist, string? Album, long? DurationSeconds);
}
