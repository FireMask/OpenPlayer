using OpenPlayer.Core.Models;

namespace OpenPlayer.Core.Interfaces;

/// <summary>Playlists guardadas; los nombres se validan con <see cref="PlaylistName.EnsureValid"/>.</summary>
public interface IPlaylistStore
{
    Task<IReadOnlyList<string>> ListAsync(CancellationToken ct = default);
    Task<LibraryPage> GetAsync(string name, int offset, CancellationToken ct = default);

    /// <summary>Crea una lista vacía; si el nombre ya existe, falla.</summary>
    Task CreateAsync(string name, CancellationToken ct = default);

    Task RenameAsync(string name, string newName, CancellationToken ct = default);
    Task DeleteAsync(string name, CancellationToken ct = default);

    /// <summary>Agrega una pista o, si <paramref name="uri"/> es una carpeta, todo su contenido.</summary>
    Task AddAsync(string name, string uri, CancellationToken ct = default);

    Task RemoveAsync(string name, int position, CancellationToken ct = default);
    Task MoveAsync(string name, int from, int to, CancellationToken ct = default);

    /// <summary>Reemplaza la cola por la lista y reproduce desde <paramref name="position"/>.</summary>
    Task PlayAsync(string name, int position, CancellationToken ct = default);
}
