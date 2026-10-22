using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Interfaces;

/// <summary>Cola de reproducción de MPD (SPEC 11); no es la biblioteca ni las playlists guardadas.</summary>
public interface IQueue
{
    /// <summary>Una página de la cola; la posición de cada pista es <c>Offset + índice</c>.</summary>
    Task<LibraryPage> GetAsync(int offset, CancellationToken ct = default);

    /// <summary>Reproduce la pista en <paramref name="position"/> (0-based).</summary>
    Task PlayAsync(int position, CancellationToken ct = default);

    /// <summary>Quita la pista con ese id de MPD (SPEC 12).</summary>
    Task RemoveAsync(int id, CancellationToken ct = default);

    /// <summary>Mueve la pista con ese id de MPD a la posición <paramref name="to"/> (0-based).</summary>
    Task MoveAsync(int id, int to, CancellationToken ct = default);

    /// <summary>Vacía la cola; MPD detiene la reproducción.</summary>
    Task ClearAsync(CancellationToken ct = default);
}
