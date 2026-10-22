using OpenPlayer.Core.Interfaces;
using OpenPlayer.Core.Models;

namespace OpenPlayer.Service.Tests;

/// <summary>Biblioteca, playlists y cola falsas: registran cada llamada en <see cref="Calls"/> o lanzan <see cref="Error"/>.</summary>
internal sealed class FakeLibrary : ILibrary, IPlaylistStore, IQueue
{
    public List<string> Calls { get; } = [];

    public Exception? Error { get; set; }

    public LibraryPage Page { get; set; } = new(0, 1, [new LibraryEntry("Rock", null)]);

    public Task<LibraryPage> BrowseAsync(string path, int offset, CancellationToken ct = default) =>
        Record($"Browse({path},{offset})", Page);

    public Task<LibraryPage> SearchAsync(string query, int offset, CancellationToken ct = default) =>
        Record($"Search({query},{offset})", Page);

    public Task PlayTrackAsync(string uri, CancellationToken ct = default) => Record($"PlayTrack({uri})", 0);

    public Task<IReadOnlyList<string>> ListAsync(CancellationToken ct = default) =>
        Record<IReadOnlyList<string>>("List", ["Viaje", "Gym"]);

    public Task<LibraryPage> GetAsync(string name, int offset, CancellationToken ct = default) =>
        Record($"Get({name},{offset})", Page);

    public Task CreateAsync(string name, CancellationToken ct = default) => Record($"Create({name})", 0);

    public Task RenameAsync(string name, string newName, CancellationToken ct = default) =>
        Record($"Rename({name},{newName})", 0);

    public Task DeleteAsync(string name, CancellationToken ct = default) => Record($"Delete({name})", 0);

    public Task AddAsync(string name, string uri, CancellationToken ct = default) => Record($"Add({name},{uri})", 0);

    public Task RemoveAsync(string name, int position, CancellationToken ct = default) =>
        Record($"Remove({name},{position})", 0);

    public Task MoveAsync(string name, int from, int to, CancellationToken ct = default) =>
        Record($"Move({name},{from},{to})", 0);

    public Task PlayAsync(string name, int position, CancellationToken ct = default) =>
        Record($"Play({name},{position})", 0);

    public Task<LibraryPage> GetAsync(int offset, CancellationToken ct = default) =>
        Record($"QueueGet({offset})", Page);

    public Task PlayAsync(int position, CancellationToken ct = default) => Record($"QueuePlay({position})", 0);

    public Task RemoveAsync(int id, CancellationToken ct = default) => Record($"QueueRemove({id})", 0);

    public Task MoveAsync(int id, int to, CancellationToken ct = default) => Record($"QueueMove({id},{to})", 0);

    public Task ClearAsync(CancellationToken ct = default) => Record("QueueClear", 0);

    // Un agregado exitoso suma un id nuevo, para que el Service lo vea en IdsAsync.
    public async Task AddAsync(string uri, bool next, CancellationToken ct = default)
    {
        await Record($"QueueAdd({uri},{next})", 0);
        Ids.Add(Ids.Count == 0 ? 1 : Ids.Max() + 1);
    }

    public Task SaveAsync(string name, CancellationToken ct = default) => Record($"QueueSave({name})", 0);

    /// <summary>Ids que devuelve <see cref="IdsAsync"/>; las pruebas los cambian para simular agregados.</summary>
    public List<int> Ids { get; set; } = [];

    public Exception? IdsError { get; set; }

    /// <summary>Veces que se activó consume; fuera de <see cref="Calls"/> porque el Service lo llama al arrancar.</summary>
    public int ConsumeCalls { get; private set; }

    public Task EnableConsumeAsync(CancellationToken ct = default)
    {
        ConsumeCalls++;
        return Error is { } e ? Task.FromException(e) : Task.CompletedTask;
    }

    public Task<IReadOnlyList<int>> IdsAsync(CancellationToken ct = default) =>
        IdsError is { } e ? Task.FromException<IReadOnlyList<int>>(e) : Task.FromResult<IReadOnlyList<int>>([.. Ids]);

    private Task<T> Record<T>(string call, T result)
    {
        Calls.Add(call);
        return Error is { } e ? Task.FromException<T>(e) : Task.FromResult(result);
    }
}
