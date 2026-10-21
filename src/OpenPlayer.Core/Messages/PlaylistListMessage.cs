using System.Text.Json;

namespace OpenPlayer.Core.Messages;

/// <summary>Respuesta IPC <c>playlist.list</c> (SPEC 10): nombres de las playlists guardadas.</summary>
public static class PlaylistListMessage
{
    public static string Serialize(IReadOnlyList<string> playlists) =>
        JsonSerializer.Serialize(new Payload("playlist.list", playlists), SnapshotMessage.Options);

    private sealed record Payload(string Type, IReadOnlyList<string> Playlists);
}
