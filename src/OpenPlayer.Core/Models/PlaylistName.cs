namespace OpenPlayer.Core.Models;

public static class PlaylistName
{
    public const int MaxLength = 100;

    /// <summary>1–100 caracteres, sin <c>/</c>, <c>\</c>, saltos de línea ni <c>.</c> inicial.</summary>
    public static string EnsureValid(string name)
    {
        if (name.Length is 0 or > MaxLength || name.StartsWith('.') || name.IndexOfAny(['/', '\\', '\n', '\r']) >= 0)
            throw new ArgumentException($"Invalid playlist name: '{name}'.", nameof(name));
        return name;
    }
}
