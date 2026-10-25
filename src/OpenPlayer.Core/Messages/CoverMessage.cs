using System.Text.Json;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Messages;

/// <summary>Respuesta IPC <c>player.cover</c> (SPEC 19): una línea JSON; <c>data</c> va en base64.</summary>
public static class CoverMessage
{
    public static string Serialize(Cover cover) =>
        JsonSerializer.Serialize(new Payload("player.cover", cover.SongId, cover.Mime, cover.Data), SnapshotMessage.Options);

    private sealed record Payload(string Type, int? SongId, string? Mime, byte[]? Data);
}
