using System.Text.Json;
using OpenPlayer.Core.Commands;

namespace OpenPlayer.Core.Messages;

/// <summary>Mensaje de entrada del socket IPC (architecture.md §7).</summary>
public abstract record IpcMessage;

public sealed record ButtonPressed(ButtonName Button, long? Sequence) : IpcMessage;

public sealed record SnapshotRequested : IpcMessage;

public sealed record SeekRequested(TimeSpan Position) : IpcMessage;

public static class IpcMessageParser
{
    /// <summary>Parsea una línea JSON. Nunca lanza: si es inválida devuelve false y un error legible para el log.</summary>
    public static bool TryParse(string line, out IpcMessage? message, out string? error)
    {
        message = null;
        try
        {
            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
                return Fail("invalid JSON", out error);
            if (!root.TryGetProperty("type", out var type) || type.ValueKind != JsonValueKind.String)
                return Fail("missing type", out error);

            switch (type.GetString())
            {
                case "button.pressed":
                    var name = root.TryGetProperty("button", out var b) ? b.ToString() : "";
                    if (b.ValueKind != JsonValueKind.String || !ButtonNames.TryParse(name, out var button))
                        return Fail($"invalid button '{name}'", out error);
                    long? sequence = null;
                    if (root.TryGetProperty("sequence", out var s))
                    {
                        if (s.ValueKind != JsonValueKind.Number || !s.TryGetInt64(out var n))
                            return Fail("invalid sequence", out error);
                        sequence = n;
                    }
                    message = new ButtonPressed(button, sequence);
                    break;
                case "player.get_snapshot":
                    message = new SnapshotRequested();
                    break;
                case "player.seek":
                    // Cota de 24 h para no desbordar TimeSpan con valores absurdos.
                    if (!root.TryGetProperty("positionSeconds", out var p) || p.ValueKind != JsonValueKind.Number
                        || !p.TryGetInt32(out var seconds) || seconds is < 0 or > 86400)
                        return Fail("invalid positionSeconds", out error);
                    message = new SeekRequested(TimeSpan.FromSeconds(seconds));
                    break;
                default:
                    return Fail($"unknown type '{type.GetString()}'", out error);
            }
            error = null;
            return true;
        }
        catch (JsonException)
        {
            return Fail("invalid JSON", out error);
        }
    }

    private static bool Fail(string reason, out string? error)
    {
        error = reason;
        return false;
    }
}
