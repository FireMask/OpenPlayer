using System.Text.Json;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Messages;

/// <summary>
/// Respuesta IPC <c>queue.page</c> (SPEC 11): pistas como en <c>library.page</c>, sin <c>directory</c>, con el <c>id</c>
/// de MPD (SPEC 12) y la etiqueta de origen <c>source</c> que recuerda el Service (SPEC 14; null si no tiene).
/// </summary>
public static class QueuePageMessage
{
    public static string Serialize(LibraryPage page, IReadOnlyDictionary<int, string> sources) => JsonSerializer.Serialize(
        new Payload(
            "queue.page",
            page.Offset,
            page.Total,
            [.. page.Entries.Select(e => new Entry(e.Uri, e.Id, e.Id is { } id ? sources.GetValueOrDefault(id) : null, e.Track?.Title, e.Track?.Artist, e.Track?.Album,
                e.Track?.Duration is { } d ? (long)d.TotalSeconds : null))]),
        SnapshotMessage.Options);

    private sealed record Payload(string Type, int Offset, int Total, IReadOnlyList<Entry> Entries);

    private sealed record Entry(string Uri, int? Id, string? Source, string? Title, string? Artist, string? Album, long? DurationSeconds);
}
