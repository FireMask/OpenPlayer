using System.Text.Json;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Messages;

/// <summary>Respuesta IPC <c>library.page</c> (SPEC 10): carpetas solo con <c>uri</c>; pistas con metadatos y <c>null</c> explícitos.</summary>
public static class LibraryPageMessage
{
    public static string Serialize(LibraryPage page) => JsonSerializer.Serialize(
        new Payload(
            "library.page",
            page.Offset,
            page.Total,
            // object: el serializador usa el tipo real de cada entrada.
            [.. page.Entries.Select(e => e.Track is { } t
                ? (object)new TrackEntry(e.Uri, false, t.Title, t.Artist, t.Album,
                    t.Duration is { } d ? (long)d.TotalSeconds : null)
                : new DirectoryEntry(e.Uri, true))]),
        SnapshotMessage.Options);

    private sealed record Payload(string Type, int Offset, int Total, IReadOnlyList<object> Entries);

    private sealed record DirectoryEntry(string Uri, bool Directory);

    private sealed record TrackEntry(string Uri, bool Directory, string? Title, string? Artist, string? Album, long? DurationSeconds);
}
