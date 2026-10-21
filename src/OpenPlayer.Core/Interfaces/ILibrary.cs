using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Interfaces;

public interface ILibrary
{
    /// <summary>Carpetas y pistas de <paramref name="path"/> (<c>""</c> = raíz), carpetas primero.</summary>
    Task<LibraryPage> BrowseAsync(string path, int offset, CancellationToken ct = default);

    /// <summary>Pistas cuyo texto contiene <paramref name="query"/> en cualquier etiqueta.</summary>
    Task<LibraryPage> SearchAsync(string query, int offset, CancellationToken ct = default);

    /// <summary>Reemplaza la cola por la pista y la reproduce.</summary>
    Task PlayTrackAsync(string uri, CancellationToken ct = default);
}
