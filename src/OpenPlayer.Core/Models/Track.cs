namespace OpenPlayer.Core.Models;

/// <param name="Uri">Ruta relativa a la biblioteca MPD. Es un dato, nunca un comando.</param>
public sealed record Track(
    string Uri,
    string? Title,
    string? Artist,
    string? Album,
    TimeSpan? Duration);
