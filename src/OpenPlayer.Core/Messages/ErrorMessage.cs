using System.Text.Json;

namespace OpenPlayer.Core.Messages;

/// <summary>Respuesta IPC <c>error</c> (architecture.md §7): una línea JSON.</summary>
public static class ErrorMessage
{
    public static string Serialize(string request, string message) =>
        JsonSerializer.Serialize(new Payload("error", request, message), SnapshotMessage.Options);

    private sealed record Payload(string Type, string Request, string Message);
}
