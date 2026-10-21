using System.Text.Json;
using OpenPlayer.Core.Commands;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Messages;

/// <summary>Mensaje de entrada del socket IPC (architecture.md §7).</summary>
public abstract record IpcMessage;

public sealed record ButtonPressed(ButtonName Button, long? Sequence) : IpcMessage;

public sealed record SnapshotRequested : IpcMessage;

public sealed record SeekRequested(TimeSpan Position) : IpcMessage;

// Biblioteca y playlists (SPEC 10): todos responden una línea (ok, página, lista o error).
public sealed record LibraryBrowseRequested(string Path, int Offset) : IpcMessage;

public sealed record LibrarySearchRequested(string Query, int Offset) : IpcMessage;

public sealed record LibraryPlayRequested(string Uri) : IpcMessage;

public sealed record PlaylistListRequested : IpcMessage;

public sealed record PlaylistGetRequested(string Name, int Offset) : IpcMessage;

public sealed record PlaylistCreateRequested(string Name) : IpcMessage;

public sealed record PlaylistRenameRequested(string Name, string NewName) : IpcMessage;

public sealed record PlaylistDeleteRequested(string Name) : IpcMessage;

public sealed record PlaylistAddRequested(string Name, string Uri) : IpcMessage;

public sealed record PlaylistRemoveRequested(string Name, int Position) : IpcMessage;

public sealed record PlaylistMoveRequested(string Name, int From, int To) : IpcMessage;

public sealed record PlaylistPlayRequested(string Name, int Position) : IpcMessage;

// Cola (SPEC 11): responden queue.page / ok / error.
public sealed record QueueGetRequested(int Offset) : IpcMessage;

public sealed record QueuePlayRequested(int Position) : IpcMessage;

public static class IpcMessageParser
{
    public const int MaxUriLength = 1024;

    /// <summary>Tipos que siempre responden; si son inválidos, el Service responde <c>error</c> con su nombre.</summary>
    private static readonly HashSet<string> ReplyingTypes =
    [
        "library.browse", "library.search", "library.play",
        "playlist.list", "playlist.get", "playlist.create", "playlist.rename", "playlist.delete",
        "playlist.add", "playlist.remove", "playlist.move", "playlist.play",
        "queue.get", "queue.play",
    ];

    /// <summary>Parsea una línea JSON. Nunca lanza: si es inválida devuelve false y un error legible para el log.</summary>
    public static bool TryParse(string line, out IpcMessage? message, out string? error) =>
        TryParse(line, out message, out error, out _);

    /// <param name="request">Tipo del mensaje si responde (SPEC 10), aunque sea inválido; si no, null.</param>
    public static bool TryParse(string line, out IpcMessage? message, out string? error, out string? request)
    {
        message = null;
        request = null;
        try
        {
            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
                return Fail("invalid JSON", out error);
            if (!root.TryGetProperty("type", out var type) || type.ValueKind != JsonValueKind.String)
                return Fail("missing type", out error);
            if (ReplyingTypes.Contains(type.GetString()!))
                request = type.GetString();

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
                case "library.browse":
                    message = new LibraryBrowseRequested(Text(root, "path", 0, MaxUriLength), Index(root, "offset", true));
                    break;
                case "library.search":
                    message = new LibrarySearchRequested(Text(root, "query", 2, 100), Index(root, "offset", true));
                    break;
                case "library.play":
                    message = new LibraryPlayRequested(Text(root, "uri", 1, MaxUriLength));
                    break;
                case "playlist.list":
                    message = new PlaylistListRequested();
                    break;
                case "playlist.get":
                    message = new PlaylistGetRequested(Name(root, "name"), Index(root, "offset", true));
                    break;
                case "playlist.create":
                    message = new PlaylistCreateRequested(Name(root, "name"));
                    break;
                case "playlist.rename":
                    message = new PlaylistRenameRequested(Name(root, "name"), Name(root, "newName"));
                    break;
                case "playlist.delete":
                    message = new PlaylistDeleteRequested(Name(root, "name"));
                    break;
                case "playlist.add":
                    message = new PlaylistAddRequested(Name(root, "name"), Text(root, "uri", 1, MaxUriLength));
                    break;
                case "playlist.remove":
                    message = new PlaylistRemoveRequested(Name(root, "name"), Index(root, "position", false));
                    break;
                case "playlist.move":
                    message = new PlaylistMoveRequested(Name(root, "name"), Index(root, "from", false), Index(root, "to", false));
                    break;
                case "playlist.play":
                    message = new PlaylistPlayRequested(Name(root, "name"), Index(root, "position", true));
                    break;
                case "queue.get":
                    message = new QueueGetRequested(Index(root, "offset", true));
                    break;
                case "queue.play":
                    message = new QueuePlayRequested(Index(root, "position", false));
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
        catch (InvalidFieldException e)
        {
            return Fail(e.Message, out error);
        }
    }

    /// <summary>Cadena JSON de <paramref name="min"/>–<paramref name="max"/> caracteres, sin caracteres de control.</summary>
    private static string Text(JsonElement root, string field, int min, int max)
    {
        if (!root.TryGetProperty(field, out var v) || v.ValueKind != JsonValueKind.String
            || v.GetString() is not { } text || text.Length < min || text.Length > max || text.Any(char.IsControl))
            throw new InvalidFieldException(field);
        return text;
    }

    private static string Name(JsonElement root, string field)
    {
        var name = Text(root, field, 1, PlaylistName.MaxLength);
        return PlaylistName.IsValid(name) ? name : throw new InvalidFieldException(field);
    }

    /// <summary>Entero JSON ≥ 0; si es opcional y falta, 0.</summary>
    private static int Index(JsonElement root, string field, bool optional)
    {
        if (!root.TryGetProperty(field, out var v))
            return optional ? 0 : throw new InvalidFieldException(field);
        if (v.ValueKind != JsonValueKind.Number || !v.TryGetInt32(out var n) || n < 0)
            throw new InvalidFieldException(field);
        return n;
    }

    private static bool Fail(string reason, out string? error)
    {
        error = reason;
        return false;
    }

    private sealed class InvalidFieldException(string field) : Exception($"invalid {field}");
}
