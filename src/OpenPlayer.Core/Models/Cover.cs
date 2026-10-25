namespace OpenPlayer.Core.Models;

/// <summary>Carátula de la pista actual (SPEC 19): imagen original, sin redimensionar.</summary>
/// <param name="SongId">Id de MPD de la pista actual, o null si no hay.</param>
/// <param name="Mime">Tipo informado por MPD (<c>image/jpeg</c>…), o null.</param>
/// <param name="Data">Bytes de la imagen, o null si la pista no tiene carátula.</param>
public sealed record Cover(int? SongId, string? Mime, byte[]? Data)
{
    public const int MaxBytes = 2 * 1024 * 1024;
}

/// <summary>La carátula pasa de <see cref="Cover.MaxBytes"/>; el Service responde <c>cover too large</c>.</summary>
public sealed class CoverTooLargeException(long size) : Exception($"cover too large ({size} bytes)")
{
    public long Size { get; } = size;
}
