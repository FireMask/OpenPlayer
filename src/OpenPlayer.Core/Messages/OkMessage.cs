using System.Text.Json;

namespace OpenPlayer.Core.Messages;

/// <summary>Respuesta IPC <c>ok</c> (SPEC 10): la operación pedida terminó bien.</summary>
public static class OkMessage
{
    public static string Serialize(string request) =>
        JsonSerializer.Serialize(new Payload("ok", request), SnapshotMessage.Options);

    private sealed record Payload(string Type, string Request);
}
