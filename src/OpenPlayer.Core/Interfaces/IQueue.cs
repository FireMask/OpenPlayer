using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Interfaces;

/// <summary>Cola de reproducción de MPD (SPEC 11); no es la biblioteca ni las playlists guardadas.</summary>
public interface IQueue
{
    /// <summary>Una página de la cola; la posición de cada pista es <c>Offset + índice</c>.</summary>
    Task<LibraryPage> GetAsync(int offset, CancellationToken ct = default);

    /// <summary>Reproduce la pista en <paramref name="position"/> (0-based).</summary>
    Task PlayAsync(int position, CancellationToken ct = default);
}
